import { copyFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
const require = createRequire(import.meta.url);
const root = path.dirname(require.resolve("swagger-ui-dist/package.json"));
for (const file of ["swagger-ui-bundle.js", "swagger-ui.css"])
  copyFileSync(path.join(root, file), path.join("dist/assets", file));
writeFileSync(
  "dist/assets/docs-init.js",
  "window.ui = SwaggerUIBundle({url:'/openapi.json',dom_id:'#swagger-ui',deepLinking:true,persistAuthorization:false,validatorUrl:null});\n",
);
