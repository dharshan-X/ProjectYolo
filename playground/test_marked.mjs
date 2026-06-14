import fs from 'fs';

const code = fs.readFileSync('desktop/renderer/vendor/marked.min.js', 'utf8');
const myModule = { exports: {} };
eval(`(function(module, exports) { ${code} })(myModule, myModule.exports);`);
const marked = myModule.exports.marked || myModule.exports;

const renderer = new marked.Renderer();
const originalCodeRenderer = renderer.code.bind(renderer);

renderer.code = function(token) {
  console.log("renderer.code called with type:", typeof token, "keys:", Object.keys(token));
  return originalCodeRenderer(token);
};

marked.setOptions({ renderer: renderer });
console.log(marked.parse("```widget\n{}\n```"));
