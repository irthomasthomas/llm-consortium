import * as babel from '@babel/core';
import * as t from '@babel/types';
import { extractComponentInfo, formatComponentContent } from '../utils/component-utils.js';

// 标准 HTML 标签列表
const STANDARD_HTML_TAGS = new Set([
  // 基础标签
  'html', 'head', 'body', 'title', 'meta', 'link', 'style', 'script',
  // 文档结构
  'header', 'nav', 'main', 'section', 'article', 'aside', 'footer',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'span',
  // 文本格式化
  'strong', 'b', 'em', 'i', 'u', 's', 'small', 'mark', 'del', 'ins',
  'sub', 'sup', 'code', 'kbd', 'samp', 'var', 'pre', 'blockquote', 'cite',
  // 列表
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  // 链接和媒体
  'a', 'img', 'audio', 'video', 'source', 'track', 'canvas', 'svg',
  'picture', 'figure', 'figcaption', 'embed', 'object', 'param', 'iframe',
  // 表格
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col',
  // 表单
  'form', 'fieldset', 'legend', 'label', 'input', 'textarea', 'select', 'option',
  'optgroup', 'button', 'datalist', 'output', 'progress', 'meter',
  // 交互元素
  'details', 'summary', 'dialog',
  // 其他常用标签
  'br', 'hr', 'wbr', 'area', 'map', 'time', 'data', 'abbr', 'address',
  'bdi', 'bdo', 'dfn', 'q', 'ruby', 'rb', 'rt', 'rtc', 'rp'
]);

// 内置的问题组件列表 - 这些组件通常来自第三方库，添加 data 属性可能会导致问题
const PROBLEMATIC_COMPONENTS = new Set([
  // Three.js / React Three Fiber 组件
  'ambientLight', 'directionalLight', 'pointLight', 'spotLight', 'hemisphereLight',
  'mesh', 'group', 'scene', 'camera', 'perspectiveCamera', 'orthographicCamera',
  'geometry', 'material', 'texture', 'Canvas', 'primitive',
  'boxGeometry', 'sphereGeometry', 'planeGeometry', 'cylinderGeometry',
  'meshBasicMaterial', 'meshStandardMaterial', 'meshPhongMaterial',
  // React Three Drei 组件
  'OrbitControls', 'TransformControls', 'Stats', 'Environment', 'Sky',
  'ContactShadows', 'BakeShadows', 'softShadows', 'Html', 'Text',
  // 其他可能有问题的第三方组件
  'Suspense', 'ErrorBoundary', 'Provider', 'Consumer'
]);

export interface ReactTransformerOptions {
  attributePrefix: string;
  includeProps: boolean;
}

export async function transformJsx(
  code: string, 
  id: string, 
  options: ReactTransformerOptions
) {
  
  const result = await babel.transformAsync(code, {
    filename: id,
    parserOpts: {
      sourceType: 'module',
      allowAwaitOutsideFunction: true,
      plugins: [
        'jsx',
        'typescript',
        'decorators-legacy',
        'classProperties',
        'objectRestSpread'
      ],
    },
    plugins: [createBabelPlugin(id, options)],
    sourceMaps: true,
  });

  if (!result || !result.code) {
    return null;
  }

  return {
    code: result.code,
    map: result.map,
  };
}

function createBabelPlugin(filePath: string, options: ReactTransformerOptions): babel.PluginItem {
  const { attributePrefix, includeProps } = options;
  
  return {
    visitor: {
      JSXOpeningElement(path, state) {
        
        // 获取组件信息
        const componentInfo = extractComponentInfo(path, filePath);
        const componentName = componentInfo.name;
        
        // 检查是否应该跳过这个组件
        if (shouldSkipComponent(componentName, PROBLEMATIC_COMPONENTS)) {
          return;
        }
        
        // 避免重复处理已经添加了标识的元素
        const hasIdentifier = path.node.attributes.some(
          (attr) => 
            t.isJSXAttribute(attr) && 
            t.isJSXIdentifier(attr.name) && 
            attr.name.name === `${attributePrefix}-id`
        );
        
        if (hasIdentifier) {
          return;
        }

        const location = path.node.loc;
        if (!location) {
          return;
        }
        
        // 构建属性列表
        const attributes = createDataAttributes(
          filePath,
          location,
          componentInfo,
          options
        );

        // 添加所有属性到元素
        attributes.forEach(attr => {
          path.node.attributes.push(attr);
        });
      },
    },
  };
}

/**
 * 检查是否应该跳过某个组件
 */
function shouldSkipComponent(
  componentName: string, 
  skipComponents: Set<string>
): boolean {
  // 检查是否在跳过组件列表中
  if (skipComponents.has(componentName)) {
    return true;
  }
  
  // 检查是否是小写字母开头但不是标准 HTML 标签的元素
  // 这类元素通常是第三方组件库的自定义元素，可能不支持任意 data 属性
  if (componentName.charAt(0) === componentName.charAt(0).toLowerCase() && 
      componentName.charAt(0) >= 'a' && componentName.charAt(0) <= 'z' &&
      !STANDARD_HTML_TAGS.has(componentName)) {
    return true;
  }
  
  return false;
}

function createDataAttributes(
  filePath: string,
  location: t.SourceLocation,
  componentInfo: {
    name: string;
    props: Record<string, any>;
  },
  options: ReactTransformerOptions
): t.JSXAttribute[] {
  const { attributePrefix, includeProps } = options;
  const { start } = location;
  
  // 提取文件信息
  const fileName = filePath.split('/').pop() || filePath;
  const relativePath = filePath.replace(process.cwd(), '').replace(/^\//, '');
  
  // 构造各种属性值
  const lovId = `${relativePath}:${start.line}:${start.column}`;
  const componentContent = includeProps ? formatComponentContent(componentInfo.props) : '';
  
  const attributes: t.JSXAttribute[] = [
    // data-lov-id
    t.jSXAttribute(
      t.jSXIdentifier(`${attributePrefix}-id`),
      t.stringLiteral(lovId)
    ),
    
    // data-lov-name
    t.jSXAttribute(
      t.jSXIdentifier(`${attributePrefix}-name`),
      t.stringLiteral(componentInfo.name)
    ),
    
    // data-component-path
    t.jSXAttribute(
      t.jSXIdentifier('data-component-path'),
      t.stringLiteral(relativePath)
    ),
    
    // data-component-line
    t.jSXAttribute(
      t.jSXIdentifier('data-component-line'),
      t.stringLiteral(start.line.toString())
    ),
    
    // data-component-file
    t.jSXAttribute(
      t.jSXIdentifier('data-component-file'),
      t.stringLiteral(fileName)
    ),
    
    // data-component-name
    t.jSXAttribute(
      t.jSXIdentifier('data-component-name'),
      t.stringLiteral(componentInfo.name)
    ),
  ];

  // 如果包含 props，添加 data-component-content
  if (includeProps && componentContent) {
    attributes.push(
      t.jSXAttribute(
        t.jSXIdentifier('data-component-content'),
        t.stringLiteral(componentContent)
      )
    );
  }

  return attributes;
}
