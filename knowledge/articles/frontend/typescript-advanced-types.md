# TypeScript 高级类型体操指南

## 前言

TypeScript 的类型系统是图灵完备的，这意味着我们可以通过类型编程实现复杂的逻辑推导。本文将深入探讨高级类型技巧，帮助你构建更加健壮的类型定义。

## 一、条件类型

### 1.1 基础条件类型

```typescript
type IsString<T> = T extends string ? true : false;

type A = IsString<string>;  // true
type B = IsString<number>;  // false

// 提取元素类型
type ElementType<T> = T extends Array<infer U> ? U : never;

type C = ElementType<string[]>;  // string
type D = ElementType<number[]>;  // number
type E = ElementType<string>;     // never
```

### 1.2 分布式条件类型

```typescript
type ToArray<T> = T extends any ? T[] : never;

type F = ToArray<string | number>;  // string[] | number[]
// 相当于: (string extends any ? string[] : never) | (number extends any ? number[] : never)
```

### 1.3 实际应用：参数类型提取

```typescript
type FunctionParams<T> = T extends (...args: infer P) => any ? P : never;

type G = FunctionParams<(name: string, age: number) => void>;  // [string, number]

// 联合类型的参数
function fetchData(id: string): Promise<string> { /* ... */ }
function fetchList(): Promise<string[]> { /* ... */ }

type H = FunctionParams<typeof fetchData | typeof fetchList>;  // [string] | []
```

## 二、映射类型

### 2.1 基础映射

```typescript
type Readonly<T> = {
  readonly [P in keyof T]: T[P];
};

type Partial<T> = {
  [P in keyof T]?: T[P];
};

type Required<T> = {
  [P in keyof T]-?: T[P];
};
```

### 2.2 键值映射

```typescript
// 将所有属性转为可选并添加前缀
type Prefixed<T, Prefix extends string> = {
  [P in keyof T as `${Prefix}${string & P}`]?: T[P];
};

interface User {
  id: string;
  name: string;
  age: number;
}

type PrefixedUser = Prefixed<User, 'user_'>;
// { user_id?: string; user_name?: string; user_age?: number }
```

### 2.3 条件映射

```typescript
type Promisable<T> = {
  [P in keyof T]: T[P] extends () => infer R ? () => Promise<R> : T[P];
};

interface SyncAPI {
  getUser(): User;
  getConfig(): Config;
}

type AsyncAPI = Promisable<SyncAPI>;
// { getUser(): Promise<User>; getConfig(): Promise<Config> }
```

## 三、模板字面量类型

### 3.1 基础用法

```typescript
type EventName = `on${Capitalize<string>}`;
type CSSUnit = `${number}px` | `${number}em` | `${number}rem`;

// 验证 CSS 单位
function setSize(size: CSSUnit) {
  document.body.style.fontSize = size;
}

setSize('16px');  // OK
setSize('1.5em'); // OK
setSize('16');    // Error
```

### 3.2 路由类型

```typescript
type ExtractRouteParams<T extends string> =
  T extends `${infer _Start}:${infer Param}/${infer Rest}`
    ? Param | ExtractRouteParams<`/${Rest}`>
    : T extends `${infer _Start}:${infer Param}`
    ? Param
    : never;

type Params = ExtractRouteParams<'/users/:userId/posts/:postId'>;
// "userId" | "postId"

function navigate<T extends string>(route: T, params: Record<ExtractRouteParams<T>, string>) {
  // 实现路由导航
}

navigate('/users/:userId/posts/:postId', { userId: '123', postId: '456' });
```

## 四、递归类型

### 4.1 深拷贝类型

```typescript
type DeepReadonly<T> = T extends (infer U)[]
  ? ReadonlyArray<DeepReadonly<U>>
  : T extends object
  ? { readonly [P in keyof T]: DeepReadonly<T[P]> }
  : T;

type Nested = {
  user: { name: string; friends: string[] };
  settings: { theme: { primary: string } };
};

type ReadonlyNested = DeepReadonly<Nested>;
// 所有嵌套属性都变为 readonly
```

### 4.2 JSON 类型

```typescript
type JSONValue = string | number | boolean | null | JSONValue[] | { [key: string]: JSONValue };

interface APISuccessResponse<T> {
  success: true;
  data: T;
  timestamp: number;
}

type JSONSuccessResponse = APISuccessResponse<JSONValue>;
```

## 五、工具类型增强

### 5.1 更强大的 PickByValue

```typescript
type PickByValue<T, V> = {
  [K in keyof T as T[K] extends V ? K : never]: T[K];
};

type StringProps = PickByValue<{ name: string; age: number; active: boolean }, string>;
// { name: string }
```

### 5.2 联合类型展开

```typescript
type Expand<T> = T extends infer O ? { [K in keyof O]: O[K] } : never;

type Union = string | { a: number } | { b: boolean };
type ExpandedUnion = Expand<Union>;
// 联合类型中的每个成员都被展开
```

## 六、实战案例

### 6.1 类型安全的 EventEmitter

```typescript
type EventMap = Record<string, any>;

type Handler<T = any> = (payload: T) => void;

class TypedEventEmitter<T extends EventMap> {
  private handlers: Partial<{ [K in keyof T]: Handler<T[K]>[] }> = {};

  on<K extends keyof T>(event: K, handler: Handler<T[K]>): this {
    if (!this.handlers[event]) {
      this.handlers[event] = [];
    }
    this.handlers[event]!.push(handler);
    return this;
  }

  emit<K extends keyof T>(event: K, payload: T[K]): void {
    const handlers = this.handlers[event];
    if (handlers) {
      handlers.forEach((handler) => handler(payload));
    }
  }
}

// 使用示例
interface AppEvents {
  userLoggedIn: { userId: string; timestamp: number };
  userLoggedOut: { userId: string };
  error: Error;
}

const emitter = new TypedEventEmitter<AppEvents>();

emitter.on('userLoggedIn', ({ userId }) => {
  console.log(`User ${userId} logged in`);
});

emitter.emit('userLoggedIn', { userId: '123', timestamp: Date.now() });
```

## 总结

TypeScript 高级类型技巧包括：
1. **条件类型**：实现类型分支逻辑
2. **映射类型**：批量转换类型结构
3. **模板字面量**：构建字符串类型模式
4. **递归类型**：处理嵌套数据结构
5. **infer 关键字**：从类型中提取子类型