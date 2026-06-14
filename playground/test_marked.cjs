const fs = require('fs');
const code = fs.readFileSync('desktop/renderer/vendor/marked.min.js', 'utf8');
const module = { exports: {} };
eval(code);
const marked = module.exports.marked || module.exports;

const renderer = new marked.Renderer();
const originalCodeRenderer = renderer.code.bind(renderer);

renderer.code = function(code, language, isEscaped) {
  // Let's see what args are passed
  console.log("renderer.code called with:");
  console.log("Arg 1:", typeof code === 'object' ? Object.keys(code) : code);
  console.log("Arg 2:", language);
  console.log("Arg 3:", isEscaped);
  return originalCodeRenderer(code, language, isEscaped);
};

marked.setOptions({ renderer: renderer });
console.log(marked.parse("```widget\n{}\n```"));
