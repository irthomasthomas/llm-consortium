# Vite Plugin Source Identifier

一个 Vite 插件，能够在开发时为 DOM 元素自动添加组件源码位置和属性信息，方便前端调试和开发者工具集成。

## 特性

- 🎯 **精确定位**: 为每个 DOM 元素添加准确的源文件路径、行号和列号
- ⚡ **高性能**: 仅在开发环境运行，对生产构建无任何影响
- 🔧 **灵活配置**: 支持自定义属性前缀、包含/排除文件等
- 📦 **框架支持**: 同时支持 React (JSX/TSX) 和 Vue 
- 🛠️ **开发友好**: 完整的 TypeScript 支持和类型提示

## 安装

```bash
npm install vite-plugin-source-identifier --save-dev
# 或
yarn add vite-plugin-source-identifier --dev
# 或
pnpm add vite-plugin-source-identifier --save-dev
```

## 使用方法

### 基础配置

在你的 `vite.config.ts` 中添加插件：

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { sourceIdentifierPlugin } from 'vite-plugin-source-identifier'

export default defineConfig({
  plugins: [
    sourceIdentifierPlugin(), // 添加在框架插件之前或之后均可
    react(),
  ],
})
```

### 高级配置

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { sourceIdentifierPlugin } from 'vite-plugin-source-identifier'

export default defineConfig({
  plugins: [
    sourceIdentifierPlugin({
      // 是否启用插件 (默认：开发环境 true，生产环境 false)
      enabled: true,
      
      // 自定义属性前缀 (默认: "data-lov")
      attributePrefix: 'data-lov',
      
      // 是否包含组件属性信息 (默认: true)
      includeProps: true,
      
      // 要处理的文件扩展名 (默认: ['.jsx', '.tsx', '.vue'])
      include: ['.jsx', '.tsx', '.vue'],
      
      // 要排除的文件模式
      exclude: ['node_modules', 'dist']
    }),
    react(),
  ],
})
```

## 生成的属性

插件会为每个 DOM 元素添加以下数据属性：

```html
<button 
  data-lov-id="src/components/Button.tsx:23:4"
  data-lov-name="button"
  data-component-path="src/components/Button.tsx"
  data-component-line="23"
  data-component-file="Button.tsx"
  data-component-name="button"
  data-component-content="%7B%22text%22%3A%22Join%20Community%22%2C%22className%22%3A%22shadow-glow%22%7D"
  class="btn-primary"
>
  Join Community
</button>
```

### 属性说明

- `data-lov-id`: 完整的源码位置标识 (文件路径:行号:列号)
- `data-lov-name`: 元素或组件名称
- `data-component-path`: 相对文件路径
- `data-component-line`: 行号
- `data-component-file`: 文件名
- `data-component-name`: 组件/元素名称
- `data-component-content`: URL 编码的组件属性 JSON (可选)

## React 示例

```tsx
// src/components/Button.tsx
import React from 'react'

interface ButtonProps {
  text: string
  className?: string
  onClick?: () => void
}

const Button: React.FC<ButtonProps> = ({ text, className, onClick }) => {
  return (
    <button className={className} onClick={onClick}>
      {text}
    </button>
  )
}

// 使用组件
<Button text="Join Community" className="shadow-glow" />
```

编译后生成：

```html
<button 
  data-lov-id="src/components/Button.tsx:12:4"
  data-lov-name="button"
  data-component-path="src/components/Button.tsx"
  data-component-line="12"
  data-component-file="Button.tsx"
  data-component-name="button"
  data-component-content="%7B%22className%22%3A%22shadow-glow%22%7D"
  class="shadow-glow"
>
  Join Community
</button>
```

## Vue 示例

```vue
<!-- src/components/Button.vue -->
<template>
  <button :class="className" @click="handleClick">
    {{ text }}
  </button>
</template>

<script setup>
interface Props {
  text: string
  className?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  click: []
}>()

const handleClick = () => {
  emit('click')
}
</script>
```

## 开发与测试

1. 克隆仓库
2. 安装依赖：`npm install`
3. 构建插件：`npm run build`
4. 运行示例：`cd examples/react-demo && npm install && npm run dev`
5. 在浏览器中打开开发者工具查看 DOM 元素的数据属性

## 技术原理

- **React/JSX**: 使用 Babel AST 解析和转换
- **Vue**: 使用 @vue/compiler-dom 进行模板转换
- **性能优化**: 仅在开发环境运行，使用高效的字符串操作库
- **Source Map**: 保持完整的调试信息和源码映射

## API 参考

### SourceIdentifierOptions

```typescript
interface SourceIdentifierOptions {
  enabled?: boolean;           // 是否启用插件
  attributePrefix?: string;    // 属性前缀
  includeProps?: boolean;      // 是否包含组件属性
  include?: string[];          // 要处理的文件扩展名
  exclude?: string[];          // 要排除的文件模式
}
```

## 许可证

MIT
## 贡献

欢迎提交 Issue 和 Pull Request！

---

**作者**: MiniMax Agent

