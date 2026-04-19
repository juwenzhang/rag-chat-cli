# Deeplink 深度链接完全指南

## 什么是 Deeplink？

Deeplink（深度链接）是一种能够在特定应用中直接打开指定页面的技术方案，无需通过应用商店或主界面导航。

## 技术分类

| 类型 | 描述 | 示例 |
|------|------|------|
| **普通 Deeplink** | 只能打开 APP | `myapp://product/123` |
| **Universal Link** | iOS 专用，HTTPS 跳转 | `https://example.com/product/123` |
| **App Link** | Android 专用 | `https://example.com/product/123` |
| **scheme** | 老式跳转协议 | `myapp://` |

## iOS Universal Link 实现

### 1. 配置文件 apple-app-site-association

放置在域名根目录 `/.well-known/apple-app-site-association`

```json
{
  "applinks": {
    "details": [
      {
        "appID": "ABCDE12345.com.example.app",
        "paths": [
          "/product/*",
          "/user/*"
        ]
      }
    ]
  }
}
```

### 2. AppDelegate 处理

```swift
func application(
  _ application: UIApplication,
  continue userActivity: NSUserActivity,
  restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
) -> Bool {
  guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
        let url = userActivity.webpageURL else {
    return false
  }

  return handleUniversalLink(url)
}

private func handleUniversalLink(_ url: URL) -> Bool {
  guard let components = URLComponents(url: url, resolvingAgainstBaseURL: true),
        let host = components.host,
        host == "example.com" else {
    return false
  }

  let path = components.path

  switch path {
  case let p where p.hasPrefix("/product/"):
    let productId = String(p.dropFirst("/product/".count))
    navigateToProduct(id: productId)
    return true

  case let p where p.hasPrefix("/user/"):
    let userId = String(p.dropFirst("/user/".count))
    navigateToUser(id: userId)
    return true

  default:
    return false
  }
}
```

## Android App Link 实现

### 1. 在 AndroidManifest.xml 配置

```xml
<intent-filter android:autoVerify="true">
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="https" android:host="example.com" />
</intent-filter>
```

### 2. 处理 App Link

```kotlin
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    private fun handleIntent(intent: Intent) {
        intent.data?.let { uri ->
            when (uri.path) {
                "/product" -> {
                    val productId = uri.getQueryParameter("id")
                    navigateToProduct(productId)
                }
                "/user" -> {
                    val userId = uri.getQueryParameter("id")
                    navigateToUser(userId)
                }
            }
        }
    }
}
```

### 3. 域名验证配置

在 `build.gradle` 中添加：

```groovy
android.defaultConfig.manifestPlaceholders = [
    asset_statements: '{ologic_destination: "\\#Intent;scheme=https;package=com.example.app;end"}'
]
```

## 唤端失败处理方案

### H5 端 Deeplink 唤端

```typescript
class DeeplinkHandler {
  private readonly APP_SCHEME = 'myapp://';
  private readonly UNIVERSAL_LINK = 'https://example.com/product/';
  private readonly FALLBACK_URL = 'https://example.com/app/download';

  async open(productId: string): Promise<void> {
    const link = `${this.UNIVERSAL_LINK}${productId}`;

    // 检测平台
    const platform = this.detectPlatform();

    if (platform === 'ios') {
      await this.openUniversalLink(link);
    } else if (platform === 'android') {
      await this.openAppLink(link);
    }
  }

  private async openUniversalLink(link: string): Promise<void> {
    const startTime = Date.now();

    // 尝试通过 iframe 唤起
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = link;
    document.body.appendChild(iframe);

    // 检测是否唤端成功
    setTimeout(() => {
      if (Date.now() - startTime < 2000) {
        document.body.removeChild(iframe);
        // 唤端失败，跳转到下载页
        window.location.href = this.FALLBACK_URL;
      }
    }, 1500);

    // 成功则直接跳转
    window.location.href = link;
  }

  private detectPlatform(): 'ios' | 'android' | 'other' {
    const userAgent = navigator.userAgent.toLowerCase();
    if (/iphone|ipad|ipod/.test(userAgent)) return 'ios';
    if (/android/.test(userAgent)) return 'android';
    return 'other';
  }
}
```

## 小程序 Deeplink

### 微信小程序

```typescript
// pages/index/index.js
Page({
  onLoad(options) {
    if (options.path && options.scene) {
      // 通过扫一扫等场景进入
      this.handleDeeplink(options.path, options.query);
    }
  },

  handleDeeplink(path: string, query: Record<string, string>) {
    // 解析 path 并跳转
    const pathMap = {
      'product': '/pages/product/detail',
      'user': '/pages/user/profile'
    };

    const targetPath = pathMap[path];
    if (targetPath) {
      wx.navigateTo({
        url: `${targetPath}?${Object.entries(query).map(([k,v]) => `${k}=${v}`).join('&')}`
      });
    }
  }
});
```

## 最佳实践

1. **务必配置备降方案**：H5 页面或应用商店链接
2. **做好兼容性检测**：iOS/Android/其他平台
3. **统计唤端成功率**：持续优化
4. **设置合理的超时时间**：避免用户长时间等待
5. **做好参数校验**：防止恶意参数注入
6. **记录来源追踪**：用于数据分析

## 性能监控

```typescript
interface DeeplinkMetrics {
  scheme: string;
  success: boolean;
  duration: number;
  platform: string;
  errorType?: string;
}

class MetricsCollector {
  trackAttempt(params: DeeplinkMetrics): void {
    // 上报埋点数据
    fetch('/api/metrics/deeplink', {
      method: 'POST',
      body: JSON.stringify(params)
    });
  }
}
```
