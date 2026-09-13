FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_WS_URL is baked into the built JS bundle at this build step -- Vite
# inlines import.meta.env.* statically, so it cannot be changed later by a
# runtime `environment:` var the way a server process's config can. See
# src/main.ts's wsUrl() for why a static build needs this at all (no
# dev-server proxy exists once `vite preview` is serving a production build).
ARG VITE_WS_URL=ws://localhost:8000/ws/session
ENV VITE_WS_URL=$VITE_WS_URL
RUN npm run build

EXPOSE 5173

CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "5173"]
