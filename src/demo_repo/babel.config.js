// Lets Jest understand JSX and modern JS in the demo repo's React code.
module.exports = {
  presets: [["@babel/preset-env", { targets: { node: "current" } }], "@babel/preset-react"],
};
