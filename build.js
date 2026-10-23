const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');

const outdir = 'src/public/dist';
if (fs.existsSync(outdir)) {
  fs.rmSync(outdir, { recursive: true });
}
fs.mkdirSync(outdir, { recursive: true });

// Single entry point - app-erp.js imports everything it needs
esbuild.build({
  entryPoints: ['src/public/js/app-erp.js'],
  bundle: true,
  format: 'esm',
  target: 'es2020',
  outdir: 'src/public/dist',
  splitting: false,  // single file
  sourcemap: false,
  minify: false,
  treeShaking: false,
  legalComments: 'none',
  define: {
    'process.env.NODE_ENV': '"production"',
  },
  loader: {
    '.css': 'text',
  },
}).then(() => {
  console.log('Build completed!');
}).catch(() => process.exit(1));