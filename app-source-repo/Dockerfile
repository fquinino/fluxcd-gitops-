FROM golang:1.25-alpine AS builder

WORKDIR /app
COPY . .
RUN go build -o app ./

FROM alpine:latest
WORKDIR /
COPY --from=builder /app/app .
CMD ["./app"]
