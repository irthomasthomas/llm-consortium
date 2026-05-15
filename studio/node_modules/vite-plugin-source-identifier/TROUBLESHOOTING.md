# Troubleshooting Guide

## Three.js / React Three Fiber Components Issue

### Problem
When using this plugin with Three.js components (like those from `@react-three/fiber`), you might encounter errors like:

```
Uncaught TypeError: Cannot read properties of undefined (reading 'matrix')
at index-5bde93f1.esm.js:667:46
at Array.reduce (<anonymous>)
at applyProps$1 (index-5bde93f1.esm.js:667:25)
```

This error occurs in components like:
- `ambientLight`
- `directionalLight`
- `mesh`
- `group`
- `Canvas`
- And other Three.js/React Three Fiber components

### Root Cause
Three.js components have very strict prop handling. When the plugin adds data attributes like `data-lov-id`, `data-component-path`, etc., these get passed as props to the Three.js components, which then try to interpret them as Three.js properties, causing internal errors.

### Solution
The plugin now automatically skips problematic components to prevent this issue. The following components and patterns are automatically excluded:

**Specific Components:**
- Three.js lights: `ambientLight`, `directionalLight`, `pointLight`, `spotLight`, `hemisphereLight`
- Three.js objects: `mesh`, `group`, `scene`, `camera`, `perspectiveCamera`, `orthographicCamera`
- Three.js primitives: `geometry`, `material`, `texture`, `Canvas`, `primitive`
- Three.js geometry: `boxGeometry`, `sphereGeometry`, `planeGeometry`, `cylinderGeometry`
- Three.js materials: `meshBasicMaterial`, `meshStandardMaterial`, `meshPhongMaterial`
- React Three Drei: `OrbitControls`, `TransformControls`, `Stats`, `Environment`, `Sky`, `ContactShadows`, `BakeShadows`, `softShadows`, `Html`, `Text`

**Pattern-based Exclusions:**
- Components ending in `Light`
- Components ending in `Geometry`
- Components ending in `Material`
- Components ending in `Controls`
- Components starting with `three`, `drei`, or `fiber` (case-insensitive)
- Components starting with lowercase letters (likely HTML elements or third-party components)

### Usage Example
```tsx
// This will work without issues now
import { Canvas } from '@react-three/fiber'

function ThreeScene() {
  return (
    <Canvas>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
      <mesh>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="orange" />
      </mesh>
    </Canvas>
  )
}
```

The plugin will automatically skip adding data attributes to all Three.js components while still processing regular React components and HTML elements.

### Manual Exclusion
If you encounter issues with other third-party components, you can exclude specific files or patterns using the plugin options:

```typescript
// vite.config.ts
export default defineConfig({
  plugins: [
    sourceIdentifierPlugin({
      // Exclude files containing Three.js components
      exclude: ['three', 'fiber', '@react-three']
    }),
    react(),
  ],
})
``` 