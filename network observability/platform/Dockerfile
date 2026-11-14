FROM node:24.11.0-alpine3.22 AS web
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13.9-slim-bookworm
ARG NAWARI_RELEASE_ID=development
ARG NAWARI_SOURCE_SHA=unknown
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV NAWARI_RELEASE_ID=${NAWARI_RELEASE_ID}
LABEL org.opencontainers.image.title="Nawari network observability platform" \
      org.opencontainers.image.version="${NAWARI_RELEASE_ID}" \
      org.opencontainers.image.revision="${NAWARI_SOURCE_SHA}"
RUN groupadd --gid 10001 nawari && useradd --uid 10001 --gid 10001 --no-create-home nawari
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt
COPY nawari/ ./nawari/
COPY --from=web /build/dist ./web/dist/
USER 10001:10001
EXPOSE 18090
ENTRYPOINT ["python", "-m", "nawari"]
CMD ["serve", "--host", "0.0.0.0", "--port", "18090"]
