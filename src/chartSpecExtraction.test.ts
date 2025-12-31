/**
 * Tests for chart spec extraction from notebook cells.
 *
 * These tests verify that:
 * 1. Vega-Lite (Altair) specs are correctly extracted from code cell outputs
 * 2. Plotly specs are correctly extracted from code cell outputs
 * 3. Both types can be extracted from the same cell
 * 4. Invalid/unsupported formats are skipped
 */

import type { IChartSpec } from './tokens';

// MIME type patterns matching promptCell.ts
const VEGALITE_MIME_PATTERN = /^application\/vnd\.vegalite\.v\d+\+json$/;
const PLOTLY_MIME = 'application/vnd.plotly.v1+json';

// Helper functions that mirror the logic in promptCell.ts
function extractChartSpecsFromOutputData(
  data: Record<string, unknown>,
  cellIndex: number,
  chartSpecs: IChartSpec[]
): void {
  // Check for Vega-Lite specs (Altair outputs)
  for (const mimeType of Object.keys(data)) {
    if (VEGALITE_MIME_PATTERN.test(mimeType)) {
      const specData = data[mimeType];
      if (specData && typeof specData === 'object') {
        chartSpecs.push({
          type: 'vega-lite',
          spec: specData as Record<string, unknown>,
          cellIndex
        });
      }
      break;
    }
  }

  // Check for Plotly specs
  const plotlyData = data[PLOTLY_MIME];
  if (plotlyData && typeof plotlyData === 'object') {
    chartSpecs.push({
      type: 'plotly',
      spec: plotlyData as Record<string, unknown>,
      cellIndex
    });
  }
}

describe('Vega-Lite (Altair) spec extraction', () => {
  it('should extract Vega-Lite v5 spec from output data', () => {
    const vegaLiteSpec = {
      $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
      data: { values: [{ x: 1, y: 2 }] },
      mark: 'bar',
      encoding: {
        x: { field: 'x', type: 'quantitative' },
        y: { field: 'y', type: 'quantitative' }
      }
    };
    const data = {
      'application/vnd.vegalite.v5+json': vegaLiteSpec,
      'text/plain': '<VegaLite 5 object>'
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(1);
    expect(chartSpecs[0].type).toBe('vega-lite');
    expect(chartSpecs[0].cellIndex).toBe(0);
    expect(chartSpecs[0].spec).toEqual(vegaLiteSpec);
  });

  it('should extract Vega-Lite v4 spec from output data', () => {
    const vegaLiteSpec = {
      $schema: 'https://vega.github.io/schema/vega-lite/v4.json',
      data: { values: [] },
      mark: 'point'
    };
    const data = {
      'application/vnd.vegalite.v4+json': vegaLiteSpec
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 3, chartSpecs);

    expect(chartSpecs).toHaveLength(1);
    expect(chartSpecs[0].type).toBe('vega-lite');
    expect(chartSpecs[0].cellIndex).toBe(3);
  });

  it('should handle complex Altair chart spec', () => {
    const complexSpec = {
      $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
      data: {
        values: [
          { category: 'A', value: 28 },
          { category: 'B', value: 55 },
          { category: 'C', value: 43 }
        ]
      },
      mark: 'bar',
      encoding: {
        x: { field: 'category', type: 'nominal', axis: { title: 'Category' } },
        y: { field: 'value', type: 'quantitative', axis: { title: 'Value' } },
        color: { field: 'category', type: 'nominal', legend: null }
      },
      title: 'Sample Bar Chart'
    };
    const data = {
      'application/vnd.vegalite.v5+json': complexSpec
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 1, chartSpecs);

    expect(chartSpecs).toHaveLength(1);
    expect(chartSpecs[0].spec).toHaveProperty('title', 'Sample Bar Chart');
    expect(chartSpecs[0].spec).toHaveProperty('encoding');
  });

  it('should not extract non-object Vega-Lite data', () => {
    const data = {
      'application/vnd.vegalite.v5+json': 'not an object'
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(0);
  });

  it('should not extract null Vega-Lite data', () => {
    const data = {
      'application/vnd.vegalite.v5+json': null
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(0);
  });
});

describe('Plotly spec extraction', () => {
  it('should extract Plotly spec from output data', () => {
    const plotlySpec = {
      data: [
        {
          x: [1, 2, 3],
          y: [4, 5, 6],
          type: 'scatter',
          mode: 'lines+markers'
        }
      ],
      layout: {
        title: 'Sample Plotly Chart'
      }
    };
    const data = {
      'application/vnd.plotly.v1+json': plotlySpec,
      'text/html': '<div id="plotly"></div>'
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 2, chartSpecs);

    expect(chartSpecs).toHaveLength(1);
    expect(chartSpecs[0].type).toBe('plotly');
    expect(chartSpecs[0].cellIndex).toBe(2);
    expect(chartSpecs[0].spec).toEqual(plotlySpec);
  });

  it('should handle Plotly with multiple traces', () => {
    const plotlySpec = {
      data: [
        { x: [1, 2], y: [1, 2], type: 'scatter', name: 'Trace 1' },
        { x: [1, 2], y: [2, 1], type: 'scatter', name: 'Trace 2' }
      ],
      layout: { title: 'Multi-trace chart' }
    };
    const data = {
      'application/vnd.plotly.v1+json': plotlySpec
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(1);
    expect((chartSpecs[0].spec as { data: unknown[] }).data).toHaveLength(2);
  });

  it('should not extract non-object Plotly data', () => {
    const data = {
      'application/vnd.plotly.v1+json': 'not an object'
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(0);
  });
});

describe('Combined extraction', () => {
  it('should extract both Vega-Lite and Plotly from same output', () => {
    const vegaLiteSpec = { mark: 'bar' };
    const plotlySpec = { data: [], layout: {} };
    const data = {
      'application/vnd.vegalite.v5+json': vegaLiteSpec,
      'application/vnd.plotly.v1+json': plotlySpec
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(2);
    expect(chartSpecs.some((s) => s.type === 'vega-lite')).toBe(true);
    expect(chartSpecs.some((s) => s.type === 'plotly')).toBe(true);
  });

  it('should accumulate specs from multiple cells', () => {
    const chartSpecs: IChartSpec[] = [];

    // Cell 0: Altair chart
    extractChartSpecsFromOutputData(
      { 'application/vnd.vegalite.v5+json': { mark: 'point' } },
      0,
      chartSpecs
    );

    // Cell 1: Plotly chart
    extractChartSpecsFromOutputData(
      { 'application/vnd.plotly.v1+json': { data: [] } },
      1,
      chartSpecs
    );

    // Cell 2: Another Altair chart
    extractChartSpecsFromOutputData(
      { 'application/vnd.vegalite.v5+json': { mark: 'bar' } },
      2,
      chartSpecs
    );

    expect(chartSpecs).toHaveLength(3);
    expect(chartSpecs[0].cellIndex).toBe(0);
    expect(chartSpecs[0].type).toBe('vega-lite');
    expect(chartSpecs[1].cellIndex).toBe(1);
    expect(chartSpecs[1].type).toBe('plotly');
    expect(chartSpecs[2].cellIndex).toBe(2);
    expect(chartSpecs[2].type).toBe('vega-lite');
  });
});

describe('Edge cases', () => {
  it('should handle empty output data', () => {
    const data = {};
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(0);
  });

  it('should ignore unsupported viz formats', () => {
    const data = {
      'application/vnd.bokehjs_load.v0+json': { some: 'data' },
      'application/vnd.holoviews_load.v0+json': { some: 'data' },
      'text/html': '<div>chart</div>'
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(0);
  });

  it('should handle text-only output data', () => {
    const data = {
      'text/plain': 'Hello, World!',
      'text/html': '<p>Hello</p>'
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(0);
  });

  it('should handle image-only output (no chart specs)', () => {
    const data = {
      'image/png': 'base64data',
      'text/plain': '<Figure>'
    };
    const chartSpecs: IChartSpec[] = [];
    extractChartSpecsFromOutputData(data, 0, chartSpecs);

    expect(chartSpecs).toHaveLength(0);
  });
});

describe('IChartSpec structure', () => {
  it('should have correct fields for Vega-Lite specs', () => {
    const chartSpec: IChartSpec = {
      type: 'vega-lite',
      spec: { mark: 'bar', encoding: {} },
      cellIndex: 5
    };

    expect(chartSpec.type).toBe('vega-lite');
    expect(chartSpec.spec).toBeDefined();
    expect(chartSpec.cellIndex).toBe(5);
  });

  it('should have correct fields for Plotly specs', () => {
    const chartSpec: IChartSpec = {
      type: 'plotly',
      spec: { data: [], layout: {} },
      cellIndex: 2
    };

    expect(chartSpec.type).toBe('plotly');
    expect(chartSpec.spec).toBeDefined();
    expect(chartSpec.cellIndex).toBe(2);
  });
});
