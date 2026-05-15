import { Plugin } from 'vite';
import { transformJsx } from './transformers/react-transformer.js';
import { transformVue } from './transformers/vue-transformer.js';

export interface SourceIdentifierOptions {
  /**
   * Whether to enable the plugin (default: true in development, false in production)
   */
  enabled?: boolean;
  
  /**
   * Custom prefix for data attributes (default: "data-lov")
   */
  attributePrefix?: string;
  
  /**
   * Whether to include component props in data-component-content (default: true)
   */
  includeProps?: boolean;
  
  /**
   * File extensions to process (default: ['.jsx', '.tsx', '.vue'])
   */
  include?: string[];
  
  /**
   * File patterns to exclude
   */
  exclude?: string[];
}

export function sourceIdentifierPlugin(options: SourceIdentifierOptions = {}): Plugin {
  const {
    enabled,
    attributePrefix = 'data-lov',
    includeProps = true,
    include = ['.jsx', '.tsx', '.vue'],
    exclude = []
  } = options;

  return {
    name: 'vite-plugin-source-identifier',
    
    // 确保在其他插件（如 @vitejs/plugin-react）之前运行
    enforce: 'pre',
    
    // 仅在开发环境生效，除非明确指定
    apply: (config, { command }) => {
      if (enabled !== undefined) {
        return enabled;
      }
      return command === 'serve'; // 仅在开发服务器模式下生效
    },

    async transform(code, id) {
      
      // 跳过 node_modules
      if (id.includes('node_modules')) {
        return null;
      }

      // 检查是否在排除列表中
      if (exclude.some(pattern => id.includes(pattern))) {
        return null;
      }

      // 检查文件扩展名
      const shouldProcess = include.some(ext => id.endsWith(ext));
      if (!shouldProcess) {
        return null;
      }

      try {
        // 根据文件类型分发给不同的转换器
        if (id.endsWith('.jsx') || id.endsWith('.tsx')) {
          // 使用 Babel 处理 React 组件
          return await transformJsx(code, id, {
            attributePrefix,
            includeProps
          });
        }

        if (id.endsWith('.vue')) {
          // 使用 @vue/compiler-dom 处理 Vue 组件
          return transformVue(code, id, {
            attributePrefix,
            includeProps
          });
        }
      } catch (error) {
        // 在转换失败时，记录错误但不中断构建过程
        return null;
      }
      
      // 对其他文件不作处理
      return null;
    },
  };
}

// 默认导出
export default sourceIdentifierPlugin;
