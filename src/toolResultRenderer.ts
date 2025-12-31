/**
 * Utility functions for rendering tool results as markdown.
 */

export interface ToolResult {
  type?: string;
  content?: string;
  format?: string;
  status?: string;
  error?: string;
}

/**
 * Render a structured tool result into markdown.
 */
export function renderToolResult(result: unknown): string {
  if (!result || typeof result !== 'object') {
    return `\n**Tool Result:** ${JSON.stringify(result)}\n`;
  }

  const resultObj = result as ToolResult;
  
  // Handle error status
  if (resultObj.status === 'error' || resultObj.error) {
    return `\n**Tool Error:** ${resultObj.error || 'Unknown error'}\n`;
  }

  const type = resultObj.type;
  const content = resultObj.content ?? '';

  if (type === 'text') {
    return `\n**Tool Result:**\n\`\`\`\n${content}\n\`\`\`\n`;
  }

  if (type === 'html') {
    // Raw HTML is allowed in Jupyter markdown
    return `\n**Tool Result (HTML):**\n\n${content}\n`;
  }

  if (type === 'image') {
    const format = resultObj.format || 'png';
    return `\n**Tool Result:**\n\n![](data:image/${format};base64,${content})\n`;
  }

  // Fallback
  return `\n**Tool Result:**\n\`\`\`json\n${JSON.stringify(result, null, 2)}\n\`\`\`\n`;
}
