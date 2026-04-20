/**
 * 修复模型输出的 JSON 中「在应用层本该是 ASCII " 的位置误用弯引号 “ ”」的问题。
 *
 * 不能对全文做 \u201c/\u201d → " 替换：字段值内合法的弯引号（如 intent 内强调）会变成未转义的 "，反而破坏 JSON。
 * 仅替换出现在 JSON 结构边界处的弯引号（逗号/冒号/括号后开串、串结束前闭串等）。
 */
export function repairStructuralSmartQuotes(s: string): string {
  let out = s;
  out = out.replace(/,\s*\u201c/g, ', "');
  out = out.replace(/\u201d\s*,/g, '",');
  out = out.replace(/\u201d\s*\]/g, '"]');
  out = out.replace(/\u201d\s*\}/g, '"}');
  out = out.replace(/:\s*\u201c/g, ': "');
  out = out.replace(/\[\s*\u201c/g, '["');
  out = out.replace(/\{\s*\u201c/g, '{ "');
  out = out.replace(/\u201d\s*:/g, '":');
  return out;
}
