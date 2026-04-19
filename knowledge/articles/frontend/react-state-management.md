# React 状态管理深度解析：Redux vs Zustand vs Jotai

## 前言

随着 React 应用复杂度的提升，状态管理成为前端架构中最核心的议题之一。本文将从设计理念、性能表现、开发体验等多个维度，深入对比三大主流状态管理方案。

## 一、Redux 核心架构

### 1.1 单一数据源

```typescript
// store/index.ts
import { configureStore } from '@reduxjs/toolkit';
import userReducer from './slices/userSlice';
import orderReducer from './slices/orderSlice';

export const store = configureStore({
  reducer: {
    user: userReducer,
    order: orderReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['order/uploadLargeFile'],
      },
    }),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
```

### 1.2 Slice 模式

```typescript
// store/slices/userSlice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface UserState {
  profile: UserProfile | null;
  isLoading: boolean;
  error: string | null;
}

const initialState: UserState = {
  profile: null,
  isLoading: false,
  error: null,
};

const userSlice = createSlice({
  name: 'user',
  initialState,
  reducers: {
    fetchStart: (state) => {
      state.isLoading = true;
      state.error = null;
    },
    fetchSuccess: (state, action: PayloadAction<UserProfile>) => {
      state.profile = action.payload;
      state.isLoading = false;
    },
    fetchFailure: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.isLoading = false;
    },
  },
});

export const { fetchStart, fetchSuccess, fetchFailure } = userSlice.actions;
export default userSlice.reducer;
```

### 1.3 RTK Query 数据获取

```typescript
// store/api/BaseApi.ts
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

export const baseApi = createApi({
  reducerPath: 'baseApi',
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  tagTypes: ['User', 'Product', 'Order'],
  endpoints: (builder) => ({
    getUser: builder.query<User, string>({
      query: (id) => `users/${id}`,
      providesTags: (result, error, id) => [{ type: 'User', id }],
    }),
    updateUser: builder.mutation<User, Partial<User> & { id: string }>({
      query: ({ id, ...patch }) => ({
        url: `users/${id}`,
        method: 'PATCH',
        body: patch,
      }),
      invalidatesTags: (result, error, { id }) => [{ type: 'User', id }],
    }),
  }),
});

export const { useGetUserQuery, useUpdateUserMutation } = baseApi;
```

## 二、Zustand 轻量方案

### 2.1 简洁 API 设计

```typescript
// stores/useUserStore.ts
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface UserStore {
  user: User | null;
  isLoading: boolean;
  setUser: (user: User) => void;
  clearUser: () => void;
}

export const useUserStore = create<UserStore>()(
  devtools(
    persist(
      (set) => ({
        user: null,
        isLoading: false,
        setUser: (user) => set({ user, isLoading: false }),
        clearUser: () => set({ user: null }),
      }),
      { name: 'user-storage' }
    ),
    { name: 'UserStore' }
  )
);

// 组件中使用
function UserProfile() {
  const { user, setUser } = useUserStore();

  return (
    <div>
      <h1>{user?.name}</h1>
      <button onClick={() => setUser({ name: 'New Name' })}>Update</button>
    </div>
  );
}
```

### 2.2 跨组件共享状态

```typescript
// stores/useCartStore.ts
import { create } from 'zustand';

interface CartItem {
  id: string;
  name: string;
  quantity: number;
  price: number;
}

interface CartStore {
  items: CartItem[];
  addItem: (item: CartItem) => void;
  removeItem: (id: string) => void;
  updateQuantity: (id: string, quantity: number) => void;
  total: () => number;
}

export const useCartStore = create<CartStore>((set, get) => ({
  items: [],
  addItem: (item) =>
    set((state) => {
      const existing = state.items.find((i) => i.id === item.id);
      if (existing) {
        return {
          items: state.items.map((i) =>
            i.id === item.id ? { ...i, quantity: i.quantity + 1 } : i
          ),
        };
      }
      return { items: [...state.items, { ...item, quantity: 1 }] };
    }),
  removeItem: (id) =>
    set((state) => ({ items: state.items.filter((i) => i.id !== id) })),
  updateQuantity: (id, quantity) =>
    set((state) => ({
      items: state.items.map((i) => (i.id === id ? { ...i, quantity } : i)),
    })),
  total: () => get().items.reduce((sum, item) => sum + item.price * item.quantity, 0),
}));
```

## 三、Jotai 原子化方案

### 3.1 原子（Atom）设计

```typescript
// atoms/index.ts
import { atom } from 'jotai';
import { atomWithStorage } from 'jotai/utils';

// 基础原子
export const userAtom = atom<User | null>(null);
export const isLoadingAtom = atom(false);

// 派生原子
export const userNameAtom = atom((get) => {
  const user = get(userAtom);
  return user?.name ?? 'Guest';
});

export const cartItemsAtom = atom<CartItem[]>([]);
export const cartTotalAtom = atom((get) => {
  const items = get(cartItemsAtom);
  return items.reduce((sum, item) => sum + item.price * item.quantity, 0);
});

// 持久化原子
export const themeAtom = atomWithStorage<'light' | 'dark'>('theme', 'light');

// 可写派生原子
export const userPlusAtom = atom(
  (get) => get(userAtom),
  (get, set, update: User | ((prev: User) => User)) => {
    const nextValue = typeof update === 'function' ? update(get(userAtom)) : update;
    set(userAtom, nextValue);
  }
);
```

### 3.2 在组件中使用

```typescript
// components/UserProfile.tsx
import { useAtom, useAtomValue } from 'jotai';

function UserProfile() {
  const [user, setUser] = useAtom(userAtom);
  const userName = useAtomValue(userNameAtom);

  return (
    <div>
      <h1>{userName}</h1>
      <button onClick={() => setUser({ id: '1', name: 'New Name' })}>
        Update Name
      </button>
    </div>
  );
}

// components/CartBadge.tsx
function CartBadge() {
  const items = useAtomValue(cartItemsAtom);
  const total = useAtomValue(cartTotalAtom);

  return (
    <div className="cart-badge">
      <span>{items.length} items</span>
      <span>Total: ${total}</span>
    </div>
  );
}
```

## 四、性能对比

| 特性 | Redux | Zustand | Jotai |
|------|-------|---------|-------|
| 包大小 | ~7KB | ~1KB | ~2KB |
| 学习曲线 | 陡峭 | 平缓 | 平缓 |
| DevTools | 完整 | 基础 | 有限 |
| TypeScript | 原生支持 | 原生支持 | 原生支持 |
| 性能优化 | 需要 memo | 自动优化 | 原子粒度 |

## 五、选型建议

### Redux 适用场景
- 大型企业级应用
- 需要复杂中间件逻辑
- 团队对 Redux 生态熟悉

### Zustand 适用场景
- 中小型应用
- 追求极致性能
- 喜欢 Hooks API

### Jotai 适用场景
- 需要细粒度更新
- React Server Components 配合
- 原子化设计思维