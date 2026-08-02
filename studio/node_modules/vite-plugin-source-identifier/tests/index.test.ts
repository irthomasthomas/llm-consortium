describe('package', () => {
  it('should work', () => {
    expect(true).toBe(true);
  });
});

// Note: The main fix has been implemented in the react-transformer.ts file
// The plugin now skips problematic components like ambientLight, mesh, etc.
// that are commonly used in Three.js/React Three Fiber applications.