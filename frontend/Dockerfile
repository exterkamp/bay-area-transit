# Production image: nginx serving a prebuilt Angular bundle.
#
# Nothing is built in here. Build on the host first:
#   source ~/.nvm/nvm.sh && nvm use 24
#   NODE_OPTIONS=--max-old-space-size=2048 npm run build
#   docker build -t bay-area-transit-frontend .
#
# /api/ and /healthz are proxied to http://backend:8000 (see nginx.conf).
FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist/frontend/browser/ /usr/share/nginx/html/

EXPOSE 80
