/**
 * Tests for image extraction from notebook cells.
 * 
 * These tests verify that:
 * 1. Images are correctly extracted from code cell outputs
 * 2. Images are correctly extracted from markdown cell attachments
 * 3. Only supported MIME types are extracted
 * 4. Image context is correctly structured
 */

import type { IImageContext } from './tokens';

// Re-export the supported MIME types for testing
const IMAGE_MIME_TYPES = ['image/png', 'image/jpeg', 'image/gif'] as const;

// Helper functions that mirror the logic in promptCell.ts
function extractImagesFromOutputData(
  data: Record<string, unknown>,
  cellIndex: number,
  images: IImageContext[]
): void {
  for (const mimeType of IMAGE_MIME_TYPES) {
    const imageData = data[mimeType];
    if (imageData && typeof imageData === 'string') {
      images.push({
        data: imageData,
        mimeType: mimeType as IImageContext['mimeType'],
        source: 'output',
        cellIndex
      });
      break;
    }
  }
}

function extractImagesFromAttachments(
  attachments: Record<string, Record<string, string>>,
  cellIndex: number,
  images: IImageContext[]
): void {
  for (const [_filename, mimeData] of Object.entries(attachments)) {
    if (!mimeData || typeof mimeData !== 'object') {
      continue;
    }
    for (const mimeType of IMAGE_MIME_TYPES) {
      const imageData = mimeData[mimeType];
      if (imageData && typeof imageData === 'string') {
        images.push({
          data: imageData,
          mimeType: mimeType as IImageContext['mimeType'],
          source: 'attachment',
          cellIndex
        });
        break;
      }
    }
  }
}

describe('Image extraction from code cell outputs', () => {
  it('should extract PNG image from output data', () => {
    const data = {
      'image/png': 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ',
      'text/plain': '<Figure size 640x480 with 1 Axes>'
    };
    const images: IImageContext[] = [];
    extractImagesFromOutputData(data, 0, images);

    expect(images).toHaveLength(1);
    expect(images[0].mimeType).toBe('image/png');
    expect(images[0].source).toBe('output');
    expect(images[0].cellIndex).toBe(0);
    expect(images[0].data).toBe('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ');
  });

  it('should extract JPEG image from output data', () => {
    const data = {
      'image/jpeg': '/9j/4AAQSkZJRgABAQEASABIAAD',
      'text/plain': '<Image>'
    };
    const images: IImageContext[] = [];
    extractImagesFromOutputData(data, 2, images);

    expect(images).toHaveLength(1);
    expect(images[0].mimeType).toBe('image/jpeg');
    expect(images[0].cellIndex).toBe(2);
  });

  it('should extract GIF image from output data', () => {
    const data = {
      'image/gif': 'R0lGODlhAQABAIAAAAAAAP',
      'text/plain': '<Animation>'
    };
    const images: IImageContext[] = [];
    extractImagesFromOutputData(data, 1, images);

    expect(images).toHaveLength(1);
    expect(images[0].mimeType).toBe('image/gif');
  });

  it('should prefer PNG over JPEG when both present', () => {
    const data = {
      'image/png': 'png_base64_data',
      'image/jpeg': 'jpeg_base64_data',
      'text/plain': '<Figure>'
    };
    const images: IImageContext[] = [];
    extractImagesFromOutputData(data, 0, images);

    expect(images).toHaveLength(1);
    expect(images[0].mimeType).toBe('image/png');
    expect(images[0].data).toBe('png_base64_data');
  });

  it('should not extract unsupported image types', () => {
    const data = {
      'image/svg+xml': '<svg>...</svg>',
      'image/webp': 'webp_data',
      'text/plain': '<Figure>'
    };
    const images: IImageContext[] = [];
    extractImagesFromOutputData(data, 0, images);

    expect(images).toHaveLength(0);
  });

  it('should not extract non-string image data', () => {
    const data = {
      'image/png': { nested: 'object' },
      'text/plain': '<Figure>'
    };
    const images: IImageContext[] = [];
    extractImagesFromOutputData(data, 0, images);

    expect(images).toHaveLength(0);
  });

  it('should handle empty output data', () => {
    const data = {};
    const images: IImageContext[] = [];
    extractImagesFromOutputData(data, 0, images);

    expect(images).toHaveLength(0);
  });

  it('should handle text-only output data', () => {
    const data = {
      'text/plain': 'Hello, World!',
      'text/html': '<p>Hello</p>'
    };
    const images: IImageContext[] = [];
    extractImagesFromOutputData(data, 0, images);

    expect(images).toHaveLength(0);
  });
});

describe('Image extraction from markdown cell attachments', () => {
  it('should extract single attachment', () => {
    const attachments = {
      'image.png': {
        'image/png': 'base64_png_data'
      }
    };
    const images: IImageContext[] = [];
    extractImagesFromAttachments(attachments, 1, images);

    expect(images).toHaveLength(1);
    expect(images[0].mimeType).toBe('image/png');
    expect(images[0].source).toBe('attachment');
    expect(images[0].cellIndex).toBe(1);
    expect(images[0].data).toBe('base64_png_data');
  });

  it('should extract multiple attachments', () => {
    const attachments = {
      'chart1.png': {
        'image/png': 'chart1_data'
      },
      'photo.jpg': {
        'image/jpeg': 'photo_data'
      }
    };
    const images: IImageContext[] = [];
    extractImagesFromAttachments(attachments, 0, images);

    expect(images).toHaveLength(2);
    expect(images.some((img) => img.data === 'chart1_data')).toBe(true);
    expect(images.some((img) => img.data === 'photo_data')).toBe(true);
  });

  it('should handle attachment with multiple MIME types', () => {
    const attachments = {
      'figure.png': {
        'image/png': 'png_version',
        'image/jpeg': 'jpeg_version'
      }
    };
    const images: IImageContext[] = [];
    extractImagesFromAttachments(attachments, 0, images);

    expect(images).toHaveLength(1);
    expect(images[0].mimeType).toBe('image/png');
    expect(images[0].data).toBe('png_version');
  });

  it('should skip unsupported attachment types', () => {
    const attachments = {
      'diagram.svg': {
        'image/svg+xml': '<svg>content</svg>'
      },
      'valid.png': {
        'image/png': 'png_data'
      }
    };
    const images: IImageContext[] = [];
    extractImagesFromAttachments(attachments, 0, images);

    expect(images).toHaveLength(1);
    expect(images[0].mimeType).toBe('image/png');
  });

  it('should handle empty attachments', () => {
    const attachments = {};
    const images: IImageContext[] = [];
    extractImagesFromAttachments(attachments, 0, images);

    expect(images).toHaveLength(0);
  });

  it('should handle invalid attachment structure', () => {
    const attachments = {
      'bad.png': null,
      'also_bad.png': 'not_an_object'
    } as unknown as Record<string, Record<string, string>>;
    const images: IImageContext[] = [];
    extractImagesFromAttachments(attachments, 0, images);

    expect(images).toHaveLength(0);
  });
});

describe('IImageContext structure', () => {
  it('should have correct fields for output images', () => {
    const imageContext: IImageContext = {
      data: 'base64_encoded_data',
      mimeType: 'image/png',
      source: 'output',
      cellIndex: 5
    };

    expect(imageContext.data).toBeDefined();
    expect(imageContext.mimeType).toBe('image/png');
    expect(imageContext.source).toBe('output');
    expect(imageContext.cellIndex).toBe(5);
  });

  it('should have correct fields for attachment images', () => {
    const imageContext: IImageContext = {
      data: 'base64_encoded_data',
      mimeType: 'image/jpeg',
      source: 'attachment',
      cellIndex: 2
    };

    expect(imageContext.source).toBe('attachment');
    expect(imageContext.mimeType).toBe('image/jpeg');
  });
});

describe('Multiple outputs accumulation', () => {
  it('should accumulate images from multiple cells', () => {
    const images: IImageContext[] = [];

    // Cell 0: matplotlib plot
    extractImagesFromOutputData({ 'image/png': 'plot1' }, 0, images);

    // Cell 1: markdown with attachment
    extractImagesFromAttachments(
      { 'diagram.png': { 'image/png': 'diagram' } },
      1,
      images
    );

    // Cell 2: another plot
    extractImagesFromOutputData({ 'image/png': 'plot2' }, 2, images);

    expect(images).toHaveLength(3);
    expect(images[0].cellIndex).toBe(0);
    expect(images[1].cellIndex).toBe(1);
    expect(images[2].cellIndex).toBe(2);
    expect(images[0].source).toBe('output');
    expect(images[1].source).toBe('attachment');
    expect(images[2].source).toBe('output');
  });
});
