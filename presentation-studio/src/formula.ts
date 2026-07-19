import { mathjax } from "mathjax-full/js/mathjax.js";
import { TeX } from "mathjax-full/js/input/tex.js";
import { SVG } from "mathjax-full/js/output/svg.js";
import { liteAdaptor } from "mathjax-full/js/adaptors/liteAdaptor.js";
import { RegisterHTMLHandler } from "mathjax-full/js/handlers/html.js";
import { AllPackages } from "mathjax-full/js/input/tex/AllPackages.js";

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const document = mathjax.document("", {
  InputJax: new TeX({ packages: AllPackages }),
  OutputJax: new SVG({ fontCache: "none" })
});

export function latexToSvgDataUri(latex: string): string {
  const node = document.convert(latex, { display: true });
  const html = adaptor.outerHTML(node);
  const svgStart = html.indexOf("<svg");
  const svg = svgStart >= 0 ? html.slice(svgStart).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ') : html;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}
