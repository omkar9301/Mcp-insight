FROM node:20-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ARG VITE_INGESTION_URL=http://localhost:8000
ARG VITE_CLASSIFIER_URL=http://localhost:8100
ENV VITE_INGESTION_URL=$VITE_INGESTION_URL
ENV VITE_CLASSIFIER_URL=$VITE_CLASSIFIER_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
