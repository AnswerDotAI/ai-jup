/**
 * Tests for toolResultRenderer.ts
 */

import { renderToolResult } from './toolResultRenderer';

describe('renderToolResult', () => {
  describe('text results', () => {
    it('should render text result with code fence', () => {
      const result = renderToolResult({ type: 'text', content: '42' });
      expect(result).toContain('**Tool Result:**');
      expect(result).toContain('```');
      expect(result).toContain('42');
    });

    it('should handle multiline text content', () => {
      const result = renderToolResult({ type: 'text', content: 'line1\nline2\nline3' });
      expect(result).toContain('line1\nline2\nline3');
    });

    it('should handle empty text content', () => {
      const result = renderToolResult({ type: 'text', content: '' });
      expect(result).toContain('```\n\n```');
    });
  });

  describe('HTML results', () => {
    it('should render HTML result directly', () => {
      const html = '<table><tr><td>data</td></tr></table>';
      const result = renderToolResult({ type: 'html', content: html });
      expect(result).toContain('**Tool Result (HTML):**');
      expect(result).toContain(html);
    });

    it('should preserve complex HTML', () => {
      const html = '<div class="foo"><span id="bar">test</span></div>';
      const result = renderToolResult({ type: 'html', content: html });
      expect(result).toContain(html);
    });
  });

  describe('image results', () => {
    it('should render PNG image as data URL', () => {
      const base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ';
      const result = renderToolResult({ type: 'image', format: 'png', content: base64 });
      expect(result).toContain('![](data:image/png;base64,');
      expect(result).toContain(base64);
    });

    it('should render JPEG image', () => {
      const base64 = '/9j/4AAQSkZJRgABAQAAAQ';
      const result = renderToolResult({ type: 'image', format: 'jpeg', content: base64 });
      expect(result).toContain('data:image/jpeg;base64,');
    });

    it('should default to PNG format', () => {
      const result = renderToolResult({ type: 'image', content: 'abc123' });
      expect(result).toContain('data:image/png;base64,');
    });
  });

  describe('error results', () => {
    it('should render error with status=error', () => {
      const result = renderToolResult({ status: 'error', error: 'Something went wrong' });
      expect(result).toContain('**Tool Error:**');
      expect(result).toContain('Something went wrong');
    });

    it('should render error when error field present', () => {
      const result = renderToolResult({ error: 'Division by zero' });
      expect(result).toContain('**Tool Error:**');
      expect(result).toContain('Division by zero');
    });

    it('should handle error without message', () => {
      const result = renderToolResult({ status: 'error' });
      expect(result).toContain('Unknown error');
    });
  });

  describe('fallback handling', () => {
    it('should render null as JSON', () => {
      const result = renderToolResult(null);
      expect(result).toContain('**Tool Result:**');
      expect(result).toContain('null');
    });

    it('should render undefined as JSON', () => {
      const result = renderToolResult(undefined);
      expect(result).toContain('**Tool Result:**');
    });

    it('should render primitive as JSON', () => {
      const result = renderToolResult(42 as unknown);
      expect(result).toContain('42');
    });

    it('should render unknown object type as JSON', () => {
      const result = renderToolResult({ foo: 'bar', baz: 123 });
      expect(result).toContain('```json');
      expect(result).toContain('"foo": "bar"');
      expect(result).toContain('"baz": 123');
    });

    it('should handle object with unknown type field', () => {
      const result = renderToolResult({ type: 'unknown', content: 'data' });
      expect(result).toContain('```json');
    });
  });

  describe('missing content', () => {
    it('should handle missing content in text type', () => {
      const result = renderToolResult({ type: 'text' });
      expect(result).toContain('```\n\n```');
    });

    it('should handle missing content in html type', () => {
      const result = renderToolResult({ type: 'html' });
      expect(result).toContain('**Tool Result (HTML):**');
    });
  });
});
