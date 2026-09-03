"""Test-session setup.

The suite imports torch indirectly: checking which engines are installed imports
each backend. On Linux that leaves torch's inter-op thread pool to be torn down
at interpreter shutdown, and some builds abort there with

    terminate called without an active exception

— a C++ std::terminate raised *after* every test has passed, which surfaces as
exit code 134 and turns a green run red. Pinning the thread pools to one thread
before torch is ever imported avoids creating the pool that fails to join.

None of this affects real use: it is set here, not in the package, because a
narration should use every core it can.
"""
import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
