/**
 * React/JS auto-fixer (jscodeshift).
 *
 * applyFix(source, finding) rewrites exactly ONE finding and returns the new
 * source, or throws FixNotSupported with a reason. Like python_fixer.py it
 * never touches the disk; recast (inside jscodeshift) reprints only the nodes
 * we changed, so the rest of the file keeps its formatting.
 *
 * CLI (used by the Python pipeline):
 *   echo '{"source": "...", "finding": {...}}' | node react_fixer.js
 *   -> {"ok": true, "source": "..."}  or  {"ok": false, "reason": "..."}
 */
"use strict";

const { scanSource, reactBaseClass, parserFor, locOf, keyName } = require("../scanner/react_scanner");

class FixNotSupported extends Error {}

function applyFix(source, finding) {
  const j = parserFor(finding.file);
  const root = j(source);

  // Re-scan the same tree and pick the node at the recorded position.
  // (scanSource parses its own copy, so we match on position against our tree.)
  const targetLoc = (p) => {
    const loc = locOf(p);
    return loc.start.line === finding.line && loc.start.column === finding.column;
  };

  let fixed;
  if (finding.rule_id === "RX004") fixed = fixDefaultProps(j, root, targetLoc);
  else if (finding.rule_id === "RX001") fixed = fixSimpleClass(j, root, targetLoc);
  else throw new FixNotSupported(`No automated fix for ${finding.rule_id}.`);

  // recast defaults to the OS line ending (\r\n on Windows); keep the file's own,
  // otherwise every line would show up as changed in the diff.
  const lineTerminator = source.includes("\r\n") ? "\r\n" : "\n";
  const output = root.toSource({ quote: "auto", lineTerminator });
  // Safety check: the output must still parse.
  try {
    scanSource(output, finding.file).forEach((r) => {
      if (r.finding.rule_id === "RX000") throw new Error(r.finding.message);
    });
  } catch (err) {
    throw new FixNotSupported(`Rewrite produced unparseable code: ${err.message}`);
  }
  if (!fixed) throw new FixNotSupported("The flagged code was not found at the recorded position.");
  return output;
}

// ---------------------------------------------------------------------------
// RX004: Comp.defaultProps = { a: 1 }   ->   function Comp({ a = 1 }) {...}
// ---------------------------------------------------------------------------
function fixDefaultProps(j, root, isTarget) {
  const statement = root.find(j.ExpressionStatement).filter(isTarget).paths()[0];
  if (!statement) return false;
  const assign = statement.node.expression;
  const compName = assign.left.object.name;

  if (assign.right.type !== "ObjectExpression") throw new FixNotSupported("defaultProps is not an object literal.");
  const defaults = [];
  for (const prop of assign.right.properties) {
    if ((prop.type !== "ObjectProperty" && prop.type !== "Property") || prop.computed || prop.key.type !== "Identifier") {
      throw new FixNotSupported("defaultProps contains spreads or computed keys.");
    }
    defaults.push({ key: prop.key.name, value: prop.value });
  }

  // Anything else reading Comp.defaultProps (tests, HOCs) would break if we delete it.
  const otherUses = root.find(j.MemberExpression, {
    object: { type: "Identifier", name: compName },
    property: { type: "Identifier", name: "defaultProps" },
  }).filter((p) => p.parent.node !== assign);
  if (otherUses.size() > 0) throw new FixNotSupported(`${compName}.defaultProps is also read elsewhere in the file.`);

  const fn = findFunctionComponent(j, root, compName);
  if (!fn) throw new FixNotSupported(`${compName} is not a function component declared in this file.`);
  const param = fn.params[0];
  if (!param || param.type !== "ObjectPattern") {
    throw new FixNotSupported(`${compName} does not destructure its props, so defaults can't be attached to parameters.`);
  }

  const hasRest = param.properties.some((p) => p.type === "RestElement");
  for (const { key, value } of defaults) {
    const entry = param.properties.find((p) => p.type !== "RestElement" && p.key && p.key.name === key);
    if (!entry) {
      // The component never reads this prop by name. Without a ...rest it is
      // simply unused; with ...rest, adding it would remove it from `rest`.
      if (hasRest) throw new FixNotSupported(`Default for "${key}" would change what ends up in ...rest.`);
      continue;
    }
    if (entry.value.type === "AssignmentPattern") {
      throw new FixNotSupported(`"${key}" already has a default parameter value.`);
    }
    // `{ color }` -> `{ color = "grey" }`; a renamed `{ color: c }` -> `{ color: c = "grey" }`.
    // Keeping the original `shorthand` flag makes recast print the short form.
    entry.value = j.assignmentPattern(entry.value, value);
  }

  j(statement).remove();
  return true;
}

function findFunctionComponent(j, root, name) {
  const decl = root.find(j.FunctionDeclaration, { id: { name } }).paths()[0];
  if (decl) return decl.node;
  const varDecl = root.find(j.VariableDeclarator, { id: { name } }).paths()[0];
  if (varDecl && ["ArrowFunctionExpression", "FunctionExpression"].includes(varDecl.node.init && varDecl.node.init.type)) {
    return varDecl.node.init;
  }
  return null;
}

// ---------------------------------------------------------------------------
// RX001: render-only class component -> function component
//   class Hello extends React.Component { render() { return <p>{this.props.name}</p>; } }
//   ->  function Hello(props) { return <p>{props.name}</p>; }
// ---------------------------------------------------------------------------
function fixSimpleClass(j, root, isTarget) {
  const classPath = root.find(j.ClassDeclaration).filter(isTarget).paths()[0];
  if (!classPath) {
    if (root.find(j.ClassExpression).filter(isTarget).size()) throw new FixNotSupported("Class expressions are not converted automatically.");
    return false;
  }
  const cls = classPath.node;
  const base = reactBaseClass(cls);
  if (base === "PureComponent") {
    throw new FixNotSupported("PureComponent skips re-renders on equal props; the equivalent needs React.memo, which changes the export.");
  }
  const members = cls.body.body;
  const extra = members.filter((m) => keyName(m) !== "render");
  if (extra.length) {
    throw new FixNotSupported(`Class has more than render(): ${extra.map(keyName).join(", ")} - needs hooks designed by hand.`);
  }
  // Babel calls methods ClassMethod (body on the node); the ESTree shape is
  // MethodDefinition (body on node.value). jscodeshift may give either.
  const render = members[0];
  const renderBody = render && (render.type === "MethodDefinition" ? render.value.body : render.body);
  if (!renderBody) throw new FixNotSupported("No render() method found.");

  // Every `this` must be part of `this.props`; anything else (state, refs, methods) needs a human.
  let usesProps = false;
  const body = j(renderBody);
  body.find(j.ThisExpression).forEach((p) => {
    const parent = p.parent.node;
    const isProps = parent.type === "MemberExpression" && parent.object === p.node && !parent.computed && parent.property.name === "props";
    if (!isProps) throw new FixNotSupported("render() uses `this` for something other than this.props.");
  });
  body.find(j.MemberExpression, { object: { type: "ThisExpression" }, property: { name: "props" } }).forEach((p) => {
    usesProps = true;
    j(p).replaceWith(j.identifier("props"));
  });

  const fn = j.functionDeclaration(j.identifier(cls.id.name), usesProps ? [j.identifier("props")] : [], renderBody);
  fn.comments = cls.comments;
  j(classPath).replaceWith(fn);

  // `import React, { Component } from "react"` -> drop Component if now unused.
  const baseName = cls.superClass.type === "Identifier" ? cls.superClass.name : null;
  if (baseName) {
    const stillUsed = root.find(j.Identifier, { name: baseName }).filter((p) => p.parent.node.type !== "ImportSpecifier").size();
    if (!stillUsed) {
      root.find(j.ImportSpecifier, { imported: { name: baseName } }).remove();
    }
  }
  return true;
}

module.exports = { applyFix, FixNotSupported };

if (require.main === module) {
  let input = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => (input += chunk));
  process.stdin.on("end", () => {
    const { source, finding } = JSON.parse(input);
    try {
      process.stdout.write(JSON.stringify({ ok: true, source: applyFix(source, finding) }));
    } catch (err) {
      const reason = err instanceof FixNotSupported ? err.message : `Fixer error: ${err.message}`;
      process.stdout.write(JSON.stringify({ ok: false, reason }));
    }
  });
}
