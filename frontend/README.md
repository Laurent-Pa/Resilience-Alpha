## Frontend (Next.js)

Stack : Next.js, React, TypeScript, Tailwind CSS.

### Lancer en local
\`\`\`bash
cd frontend
npm install
npm run dev
\`\`\`

### Lancer avec Docker
\`\`\`bash
docker build -t frontend-app ./frontend
docker run -p 3000:3000 frontend-app
\`\`\`