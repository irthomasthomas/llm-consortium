import { parse, transform, ElementNode, NodeTypes } from '@vue/compiler-dom';
import MagicString from 'magic-string';

export interface VueTransformerOptions {
  attributePrefix: string;
  includeProps: boolean;
}

export function transformVue(
  code: string, 
  id: string, 
  options: VueTransformerOptions
) {
  try {
    const s = new MagicString(code);
    
    // 解析 Vue SFC
    const ast = parse(code, {
      isNativeTag: () => false, // 允许所有标签
      getNamespace: () => 0,
    });

    // 转换 AST
    transform(ast, {
      nodeTransforms: [
        (node) => {
          if (node.type === NodeTypes.ELEMENT && node.loc) {
            addVueAttributes(node as ElementNode, id, s, options);
          }
        },
      ],
    });

    return {
      code: s.toString(),
      map: s.generateMap({ 
        source: id, 
        includeContent: true 
      }),
    };
  } catch (error) {
    console.warn(`Failed to transform Vue file ${id}:`, error);
    return null;
  }
}

function addVueAttributes(
  node: ElementNode,
  filePath: string,
  s: MagicString,
  options: VueTransformerOptions
) {
  const { attributePrefix, includeProps } = options;
  const { start } = node.loc;
  
  // 检查是否已经添加了标识属性
  const hasIdentifier = node.props.some(prop => {
    return prop.type === NodeTypes.ATTRIBUTE && 
           prop.name === `${attributePrefix}-id`;
  });
  
  if (hasIdentifier) {
    return;
  }

  // 提取文件信息
  const fileName = filePath.split('/').pop() || filePath;
  const relativePath = filePath.replace(process.cwd(), '').replace(/^\//, '');
  
  // 构造属性值
  const lovId = `${relativePath}:${start.line}:${start.column}`;
  const componentName = node.tag;
  
  // 提取组件属性
  const componentProps = extractVueProps(node);
  const componentContent = includeProps ? formatVueComponentContent(componentProps) : '';
  
  // 构建要插入的属性字符串
  const attributes = [
    `${attributePrefix}-id="${lovId}"`,
    `${attributePrefix}-name="${componentName}"`,
    `data-component-path="${relativePath}"`,
    `data-component-line="${start.line}"`,
    `data-component-file="${fileName}"`,
    `data-component-name="${componentName}"`,
  ];

  if (includeProps && componentContent) {
    attributes.push(`data-component-content="${componentContent}"`);
  }

  const attributeString = ' ' + attributes.join(' ');
  
  // 找到插入位置 - 在标签名之后
  const tagStart = start.offset;
  const tagSource = s.slice(tagStart, tagStart + 100); // 取一段来分析
  const tagNameEnd = tagSource.indexOf(' ') !== -1 ? 
    tagStart + tagSource.indexOf(' ') : 
    tagStart + node.tag.length + 1;
  
  // 插入属性
  s.prependLeft(tagNameEnd, attributeString);
}

function extractVueProps(node: ElementNode): Record<string, any> {
  const props: Record<string, any> = {};
  
  node.props.forEach(prop => {
    if (prop.type === NodeTypes.ATTRIBUTE) {
      // 静态属性
      props[prop.name] = prop.value?.content || true;
    } else if (prop.type === NodeTypes.DIRECTIVE) {
      // 指令属性
      const argContent = prop.arg && 'content' in prop.arg ? prop.arg.content : 'bind';
      const name = prop.name === 'bind' ? argContent : prop.name;
      const expContent = prop.exp && 'content' in prop.exp ? prop.exp.content : true;
      props[`:${name}`] = expContent;
    }
  });
  
  return props;
}

function formatVueComponentContent(props: Record<string, any>): string {
  try {
    // 过滤掉不需要的属性
    const filteredProps = Object.fromEntries(
      Object.entries(props).filter(([key]) => 
        !key.startsWith('data-') && 
        !key.startsWith('v-') &&
        key !== 'key' &&
        key !== 'ref'
      )
    );
    
    if (Object.keys(filteredProps).length === 0) {
      return '';
    }
    
    const jsonString = JSON.stringify(filteredProps);
    return encodeURIComponent(jsonString);
  } catch (error) {
    console.warn('Failed to format Vue component content:', error);
    return '';
  }
}
