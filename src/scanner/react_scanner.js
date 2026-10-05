/**
 * React/JS legacy-pattern scanner (jscodeshift).
 *
 * Same idea as python_scanner.py: parse each file into a syntax tree, look for
 * a curated list of patterns (src/rules/react_rules.json), and emit findings.
 *
 * CLI:   node react_scanner.js <repo-root>      -> prints {"files": [...], "findings": [...]}
 * Module: scanSource(source, relPath) is used by react_fixer.js and the unit tests.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const jscodeshift = require("jscodeshift");

const SKIP_DIRS = new Set(["node_modules", ".git", "build", "dist", "coverage", "__tests__"]);
const MAX_SNIPPET_LINES = 8;

const EFFECT_LIFECYCLES = new Set(["componentDidMount", "componentDidUpdate", "componentWillUnmount"]);
const UNSAFE_LIFECYCLES = new Set([
  "componentWillMount", "componentWillReceiveProps", "componentWillUpdate",
  "UNSAFE_componentWillMount", "UNSAFE_componentWillReceiveProps", "UNSAFE_componentWillUpdate",
]);

/** jscodeshift bound to the right parser for the file type. */
function parserFor(relPath) {
  return jscodeshift.withParser(relPath.endsWith(".tsx") ? "tsx" : relPath.endsWith(".ts") ? "ts" : "babel");
}

function isTestOrConfig(name) {
  return /\.(test|spec)\.[jt]sx?$/.test(name) || /\.config\.[jt]s$/.test(name);
}

/** `extends Component`, `extends React.PureComponent`, ... -> "Component" | "PureComponent" | null */
function reactBaseClass(classNode) {
  const sc = classNode.superClass;
  if (!sc) return null;
  const name = sc.type === "Identifier" ? sc.name
    : sc.type === "MemberExpression" && sc.object.name === "React" ? sc.property.name
    : null;
  return name === "Component" || name === "PureComponent" ? name : null;
}

function keyName(node) {
  return node.key && (node.key.name || node.key.value);
}

/**
 * Location of the node at `nodePath`. recast drops `loc` on a class declared as
 * `export default class X ...`; the surrounding export statement keeps it, so
 * we report the finding at the start of that statement instead.
 */
function locOf(nodePath) {
  if (nodePath.node.loc) return nodePath.node.loc;
  const parent = nodePath.parent && nodePath.parent.node;
  if (parent && /^Export/.test(parent.type) && parent.loc) return parent.loc;
  throw new Error(`No source location for ${nodePath.node.type}`);
}

/**
 * Scan one file. Returns [{finding, path}] - `path` is the jscodeshift NodePath,
 * which the fixer needs; the CLI only prints the findings.
 */
function scanSource(source, relPath) {
  const j = parserFor(relPath);
  let root;
  try {
    root = j(source);
  } catch (err) {
    const line = (err.loc && err.loc.line) || 1;
    return [{ finding: makeFinding("RX000", relPath, source, { start: { line, column: 0 }, end: { line } },
      `File could not be parsed: ${err.message.split("\n")[0]}`, true), path: null }];
  }

  const results = [];
  const add = (ruleId, nodePath, message, headerOnly = false) => {
    results.push({ finding: makeFinding(ruleId, relPath, source, locOf(nodePath), message, headerOnly), path: nodePath });
  };

  // RX001 class components, plus RX002/RX003 on their lifecycle methods.
  const classes = [...root.find(j.ClassDeclaration).paths(), ...root.find(j.ClassExpression).paths()];
  for (const classPath of classes) {
    const base = reactBaseClass(classPath.node);
    if (!base) continue;
    const name = classPath.node.id ? classPath.node.id.name : "(anonymous)";
    add("RX001", classPath, `\`${name}\` is a class component (extends ${base}).`, true);

    for (const member of classPath.get("body", "body").map((p) => p)) {
      const key = keyName(member.node);
      if (member.node.type !== "ClassMethod" && member.node.type !== "MethodDefinition") continue;
      if (EFFECT_LIFECYCLES.has(key)) {
        add("RX002", member, `\`${name}.${key}\` should become a useEffect hook.`, true);
      } else if (UNSAFE_LIFECYCLES.has(key)) {
        add("RX003", member, `\`${name}.${key}\` is an unsafe legacy lifecycle method.`, true);
      }
    }
  }

  // RX004 `Comp.defaultProps = {...}`   RX005 `Comp.propTypes = {...}`
  root.find(j.AssignmentExpression, { left: { type: "MemberExpression" } }).forEach((p) => {
    const { object, property } = p.node.left;
    if (object.type !== "Identifier" || property.type !== "Identifier") return;
    const statement = p.parent.node.type === "ExpressionStatement" ? p.parent : p;
    if (property.name === "defaultProps") {
      add("RX004", statement, `\`${object.name}.defaultProps\` should become default parameter values.`);
    } else if (property.name === "propTypes") {
      add("RX005", statement, `\`${object.name}.propTypes\` uses runtime PropTypes checking.`);
    }
  });

  // RX005 also covers `static propTypes = {...}` inside classes.
  root.find(j.ClassProperty, { static: true }).forEach((p) => {
    if (keyName(p.node) === "propTypes") add("RX005", p, "Class declares `static propTypes`.");
  });

  results.sort((a, b) => a.finding.line - b.finding.line || a.finding.column - b.finding.column);
  return results;
}

function makeFinding(ruleId, relPath, source, loc, message, headerOnly = false) {
  const lines = source.split(/\r?\n/);
  const start = loc.start.line;
  const end = loc.end.line;
  const last = headerOnly ? start : Math.min(end, start + MAX_SNIPPET_LINES - 1);
  return {
    rule_id: ruleId,
    language: "react",
    file: relPath,
    line: start,
    column: loc.start.column,
    end_line: end,
    snippet: lines.slice(start - 1, last).join("\n"),
    message,
  };
}

function findReactFiles(root) {
  const out = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) walk(full);
      } else if (/\.(jsx?|tsx)$/.test(entry.name) && !isTestOrConfig(entry.name)) {
        out.push(full);
      }
    }
  };
  walk(root);
  return out;
}

function scanPath(root) {
  const files = findReactFiles(root);
  const findings = [];
  for (const file of files) {
    const rel = path.relative(root, file).split(path.sep).join("/");
    for (const r of scanSource(fs.readFileSync(file, "utf8"), rel)) findings.push(r.finding);
  }
  return { files: files.map((f) => path.relative(root, f).split(path.sep).join("/")), findings };
}

module.exports = { scanSource, scanPath, reactBaseClass, parserFor, locOf, keyName };

if (require.main === module) {
  const root = process.argv[2];
  if (!root) {
    console.error("usage: node react_scanner.js <repo-root>");
    process.exit(2);
  }
  process.stdout.write(JSON.stringify(scanPath(path.resolve(root))));
}
