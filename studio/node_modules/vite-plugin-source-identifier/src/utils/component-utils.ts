import * as t from '@babel/types';
import { NodePath } from '@babel/traverse';

/**
 * 从 JSX 路径中提取组件信息
 */
export function extractComponentInfo(
  path: NodePath<t.JSXOpeningElement>,
  filePath: string
): {
  name: string;
  props: Record<string, any>;
} {
  const elementName = getElementName(path.node.name);
  const props = extractProps(path.node.attributes);
  
  return {
    name: elementName,
    props
  };
}

/**
 * 获取 JSX 元素名称
 */
function getElementName(name: t.JSXElement['openingElement']['name']): string {
  if (t.isJSXIdentifier(name)) {
    return name.name;
  } else if (t.isJSXMemberExpression(name)) {
    // 处理 Namespace.Component 这样的情况
    return `${getElementName(name.object)}.${name.property.name}`;
  } else if (t.isJSXNamespacedName(name)) {
    // 处理 namespace:name 这样的情况
    return `${name.namespace.name}:${name.name.name}`;
  }
  
  return 'Unknown';
}

/**
 * 提取 JSX 属性
 */
function extractProps(attributes: (t.JSXAttribute | t.JSXSpreadAttribute)[]): Record<string, any> {
  const props: Record<string, any> = {};
  
  attributes.forEach(attr => {
    if (t.isJSXAttribute(attr)) {
      const name = t.isJSXIdentifier(attr.name) 
        ? attr.name.name 
        : `${attr.name.namespace.name}:${attr.name.name.name}`;
      
      const value = extractAttributeValue(attr.value);
      props[name] = value;
    } else if (t.isJSXSpreadAttribute(attr)) {
      // 对于展开属性，我们只能记录它的存在
      props['...spread'] = true;
    }
  });
  
  return props;
}

/**
 * 提取 JSX 属性值
 */
function extractAttributeValue(value: t.JSXAttribute['value']): any {
  if (!value) {
    return true; // 无值的属性默认为 true
  }
  
  if (t.isStringLiteral(value)) {
    return value.value;
  }
  
  if (t.isJSXExpressionContainer(value)) {
    const expression = value.expression;
    
    if (t.isStringLiteral(expression)) {
      return expression.value;
    } else if (t.isNumericLiteral(expression)) {
      return expression.value;
    } else if (t.isBooleanLiteral(expression)) {
      return expression.value;
    } else if (t.isNullLiteral(expression)) {
      return null;
    } else if (t.isObjectExpression(expression)) {
      // 简单对象字面量
      const obj: Record<string, any> = {};
      expression.properties.forEach(prop => {
        if (t.isObjectProperty(prop) && !prop.computed) {
          const key = t.isIdentifier(prop.key) ? prop.key.name : String(prop.key);
          const val = extractObjectPropertyValue(prop.value);
          obj[key] = val;
        }
      });
      return obj;
    } else if (t.isArrayExpression(expression)) {
      // 简单数组字面量
      return expression.elements.map(element => {
        if (!element || t.isSpreadElement(element)) return null;
        return extractObjectPropertyValue(element);
      });
    }
    
    // 对于复杂表达式，返回其类型
    return `[${expression.type}]`;
  }
  
  return null;
}

/**
 * 提取对象属性值
 */
function extractObjectPropertyValue(node: t.Expression | t.PatternLike): any {
  if (t.isStringLiteral(node)) {
    return node.value;
  } else if (t.isNumericLiteral(node)) {
    return node.value;
  } else if (t.isBooleanLiteral(node)) {
    return node.value;
  } else if (t.isNullLiteral(node)) {
    return null;
  } else if (t.isIdentifier(node)) {
    return `[var:${node.name}]`;
  }
  
  return `[${node.type}]`;
}

/**
 * 格式化组件内容为 URL 编码的 JSON 字符串
 */
export function formatComponentContent(props: Record<string, any>): string {
  try {
    // 过滤掉一些不需要的属性
    const filteredProps = Object.fromEntries(
      Object.entries(props).filter(([key]) => 
        !key.startsWith('data-') && 
        !key.startsWith('aria-') &&
        key !== 'key' &&
        key !== 'ref'
      )
    );
    
    // 如果没有有效的 props，返回空字符串
    if (Object.keys(filteredProps).length === 0) {
      return '';
    }
    
    const jsonString = JSON.stringify(filteredProps);
    return encodeURIComponent(jsonString);
  } catch (error) {
    console.warn('Failed to format component content:', error);
    return '';
  }
}

/**
 * 判断是否为 React 组件（首字母大写）
 */
export function isReactComponent(name: string): boolean {
  return /^[A-Z]/.test(name);
}

/**
 * 判断是否为 HTML 标签
 */
export function isHTMLTag(name: string): boolean {
  return /^[a-z]/.test(name);
}
