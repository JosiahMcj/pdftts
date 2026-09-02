# The dashboard and CLI, minus OCR.
#
# OCR calls Apple's Vision framework through a Swift helper, so it cannot cross
# to Linux; a scanned PDF in this image is refused with a clear message rather
# than silently producing nothing. Everything else — every input format, every
# output format, Kokoro and Piper, the resume cache, the phone connector — works.
#
#   docker build -t pdftts .
#   docker run --rm -p 8765:8765 -v "$PWD:/books" pdftts --serve --lan
#   docker run --rm -v "$PWD:/books" pdftts /books/novel.epub --m4b
#
# Models and finished chunks live in named volumes, so a rebuilt container does
# not re-download Kokoro or re-synthesize what it already has:
#   docker run --rm -v pdftts-models:/home/reader/.cache/huggingface \
#              -v pdftts-cache:/home/reader/.cache/pdftts \
#              -v "$PWD:/books" pdftts /books/novel.epub

FROM python:3.12-slim AS build

# Torch ships a CUDA build by default and it is gigabytes of driver this image
# will never use. The CPU index keeps the layer to a fraction of that.
ENV UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu \
    UV_INDEX_STRATEGY=unsafe-best-match \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
COPY vendor ./vendor
RUN uv venv /opt/venv \
 && VIRTUAL_ENV=/opt/venv uv pip install --no-cache . \
 && find /opt/venv -name '__pycache__' -type d -prune -exec rm -rf {} +


FROM python:3.12-slim

# espeak-ng is Kokoro's fallback phonemiser; ffmpeg is needed for anything that
# is not a WAV. Both are small next to the model weights.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg espeak-ng \
 && rm -rf /var/lib/apt/lists/*

# Not root: this container is handed a directory of the user's own books.
RUN useradd --create-home --uid 1000 reader
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/home/reader/.cache/huggingface \
    XDG_CACHE_HOME=/home/reader/.cache \
    XDG_DATA_HOME=/home/reader/.local/share

USER reader
WORKDIR /books
EXPOSE 8765

# --serve alone binds 127.0.0.1, which is unreachable from outside a container.
# --lan is what makes a published port work, and it says what it exposes.
ENTRYPOINT ["pdftts"]
CMD ["--serve", "--lan"]
