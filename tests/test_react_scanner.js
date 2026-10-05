/**
 * Unit tests for src/scanner/react_scanner.js and src/fixer/react_fixer.js.
 * Run with: npx jest
 */
const { scanSource } = require("../src/scanner/react_scanner");
const { applyFix, FixNotSupported } = require("../src/fixer/react_fixer");

const findings = (src) => scanSource(src, "Comp.jsx").map((r) => r.finding);
const ruleIds = (src) => findings(src).map((f) => f.rule_id);

/** Apply the first finding with `ruleId`. */
function fix(src, ruleId) {
  const finding = findings(src).find((f) => f.rule_id === ruleId);
  return applyFix(src, finding);
}

describe("react scanner", () => {
  test("detects class components extending Component, React.Component and PureComponent", () => {
    expect(ruleIds("class A extends Component { render() { return null; } }")).toEqual(["RX001"]);
    expect(ruleIds("class A extends React.Component { render() { return null; } }")).toEqual(["RX001"]);
    expect(ruleIds("class A extends PureComponent { render() { return null; } }")).toEqual(["RX001"]);
  });

  test("ignores classes that are not React components", () => {
    expect(ruleIds("class Store extends EventEmitter { emitIt() {} }")).toEqual([]);
  });

  test("flags effect lifecycles (RX002) and unsafe lifecycles (RX003)", () => {
    const src = `class A extends React.Component {
      componentDidMount() {}
      componentWillUnmount() {}
      componentWillReceiveProps(next) {}
      UNSAFE_componentWillMount() {}
      render() { return null; }
    }`;
    expect(ruleIds(src)).toEqual(["RX001", "RX002", "RX002", "RX003", "RX003"]);
  });

  test("flags defaultProps (RX004) and propTypes (RX005)", () => {
    const src = `const A = ({ x }) => <b>{x}</b>;
A.propTypes = { x: PropTypes.string };
A.defaultProps = { x: "hi" };`;
    expect(ruleIds(src)).toEqual(["RX005", "RX004"]);
  });

  test("modern function component has no findings", () => {
    expect(ruleIds('export function A({ x = "hi" }) { return <b>{x}</b>; }')).toEqual([]);
  });

  test("reports correct position for export default class", () => {
    const src = 'import React from "react";\n\nexport default class A extends React.Component {\n  render() { return null; }\n}\n';
    const [f] = findings(src);
    expect([f.rule_id, f.line, f.column]).toEqual(["RX001", 3, 0]);
    expect(f.snippet).toBe("export default class A extends React.Component {");
  });

  test("unparseable file becomes RX000", () => {
    expect(ruleIds("const = ;")).toEqual(["RX000"]);
  });
});

describe("react fixer", () => {
  test("RX004 moves defaultProps into destructured parameter defaults", () => {
    const src = `function Badge({ label, color }) {
  return <span className={color}>{label}</span>;
}

Badge.defaultProps = {
  color: "grey",
};
`;
    const out = fix(src, "RX004");
    expect(out).toContain('function Badge({ label, color = "grey" })');
    expect(out).not.toContain("defaultProps");
  });

  test("fixes keep the file's own line endings", () => {
    const lf = "function A({ x }) {\n  return x;\n}\nA.defaultProps = { x: 1 };\n";
    expect(fix(lf, "RX004")).not.toContain("\r\n");
    const crlf = lf.replace(/\n/g, "\r\n");
    expect(fix(crlf, "RX004").split("\r\n").length).toBeGreaterThan(2);
  });

  test("RX004 works for arrow components and renamed props", () => {
    const src = 'const A = ({ size: s }) => <i>{s}</i>;\nA.defaultProps = { size: "md" };\n';
    expect(fix(src, "RX004")).toContain('const A = ({ size: s = "md" }) =>');
  });

  test("RX004 refuses when props are not destructured", () => {
    const src = "function A(props) { return props.x; }\nA.defaultProps = { x: 1 };\n";
    expect(() => fix(src, "RX004")).toThrow(/does not destructure/);
  });

  test("RX004 refuses when a default would change ...rest", () => {
    const src = "function A({ x, ...rest }) { return <div {...rest} />; }\nA.defaultProps = { y: 1 };\n";
    expect(() => fix(src, "RX004")).toThrow(/rest/);
  });

  test("RX001 converts a render-only class into a function component", () => {
    const src = `import React, { Component } from "react";

export default class Hello extends Component {
  render() {
    return <p>Hello {this.props.name}</p>;
  }
}
`;
    const out = fix(src, "RX001");
    expect(out).toContain("export default function Hello(props) {");
    expect(out).toContain("<p>Hello {props.name}</p>");
    expect(out).toContain('import React from "react";');
    expect(out).not.toContain("class");
  });

  test("RX001 refuses classes with state or lifecycle methods", () => {
    const src = "class A extends React.Component { componentDidMount() {} render() { return null; } }";
    expect(() => fix(src, "RX001")).toThrow(/more than render/);
  });

  test("RX001 refuses PureComponent (needs React.memo)", () => {
    const src = "class A extends PureComponent { render() { return null; } }";
    expect(() => fix(src, "RX001")).toThrow(/React.memo/);
  });

  test("RX001 refuses render() that uses this.state", () => {
    const src = "class A extends React.Component { render() { return this.state.x; } }";
    expect(() => fix(src, "RX001")).toThrow(FixNotSupported);
  });

  test("review-only rules have no automated fix", () => {
    const src = "const A = () => null;\nA.propTypes = {};\n";
    expect(() => fix(src, "RX005")).toThrow(/No automated fix/);
  });
});
