FROM node:22-bookworm-slim
WORKDIR /workspace
COPY package.json package-lock.json ./
COPY apps/dashboard/package.json apps/dashboard/package.json
RUN npm ci
COPY apps/dashboard apps/dashboard
EXPOSE 3000
CMD ["npm", "run", "dev"]
