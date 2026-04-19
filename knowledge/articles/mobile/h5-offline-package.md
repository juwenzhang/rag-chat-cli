# H5 离线包技术详解

## 离线包原理

H5 离线包是一种将 Web 资源提前打包到客户端本地的技术方案，可以在没有网络或网络较差的情况下仍然保持页面的完整功能。

```
┌──────────────────────────────────────────────────────────────┐
│                        App Container                         │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   Hybrid Engine                       │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │    │
│  │  │   Router    │  │  CacheMgr   │  │  Loader     │  │    │
│  │  │  (路由拦截) │  │  (离线缓存) │  │  (资源加载) │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
│                            │                                 │
│         ┌──────────────────┼──────────────────┐            │
│         ▼                  ▼                  ▼            │
│   ┌───────────┐     ┌───────────┐     ┌───────────┐       │
│   │  Local    │     │   Mem     │     │   CDN     │       │
│   │  Package  │     │   Cache   │     │  Fallback │       │
│   └───────────┘     └───────────┘     └───────────┘       │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

## 离线包结构

```
_offline/
├── manifest.json           # 包清单
├── index.html              # 入口页面
├── static/
│   ├── css/
│   │   └── app.css
│   ├── js/
│   │   ├── vendor.js       # 第三方库
│   │   └── app.js          # 业务代码
│   └── images/
│       └── logo.png
└── _backup/                # 备用资源
    └── fallback.html
```

## Android WebView 离线方案

### 1. 拦截请求

```kotlin
class OfflineWebViewClient : WebViewClient() {

    private val offlineManager = OfflinePackageManager()

    override fun shouldInterceptRequest(
        view: WebView?,
        request: WebResourceRequest?
    ): WebResourceResponse? {
        val url = request?.url?.toString() ?: return null

        // 1. 检查内存缓存
        memoryCache.get(url)?.let { return it }

        // 2. 解析 URL 获取资源路径
        val relativePath = parseResourcePath(url) ?: return null

        // 3. 检查离线包
        val localFile = File(offlineDir, relativePath)
        if (localFile.exists()) {
            val mimeType = getMimeType(localFile.extension)
            return WebResourceResponse(
                mimeType,
                "UTF-8",
                FileInputStream(localFile)
            ).apply {
                responseHeaders = getCommonHeaders()
            }.also {
                memoryCache.put(url, it)
            }
        }

        // 4. 降级到 CDN
        return null
    }

    private fun parseResourcePath(url: String): String? {
        // 移除域名和版本号
        // https://example.com/v1.2.0/static/js/app.js -> static/js/app.js
        val pattern = Regex("/v?[\\d.]+/([^/].*)")
        return pattern.find(url)?.groupValues?.get(1)
    }
}
```

### 2. 离线包管理

```kotlin
class OfflinePackageManager(private val context: Context) {

    private val offlineDir: File by lazy {
        File(context.filesDir, "_offline").apply { mkdirs() }
    }

    private val memoryCache = LruCache<String, WebResourceResponse>(50)

    suspend fun downloadAndInstallPackage(packageInfo: PackageInfo): Result<Unit> {
        // 1. 下载离线包
        val zipFile = downloadPackage(packageInfo.downloadUrl)

        // 2. 校验 CRC
        if (!verifyCRC(zipFile, packageInfo.crc32)) {
            return Result.failure(CrcMismatchException())
        }

        // 3. 解压安装
        return withContext(Dispatchers.IO) {
            val versionDir = File(offlineDir.parentFile, "_offline_${packageInfo.version}")
            unzip(zipFile, versionDir)

            // 4. 原子性切换
            atomicSwitch(offlineDir, versionDir)

            // 5. 清理旧版本
            cleanupOldVersions(packageInfo.version)

            Result.success(Unit)
        }
    }

    private suspend fun downloadPackage(url: String): File {
        // 下载实现
    }

    private fun verifyCRC(file: File, expectedCRC: Long): Boolean {
        val crc = CRC32()
        file.inputStream().use { fis ->
            val buffer = ByteArray(8192)
            var bytesRead: Int
            while (fis.read(buffer).also { bytesRead = it } != -1) {
                crc.update(buffer, 0, bytesRead)
            }
        }
        return crc.value == expectedCRC
    }
}
```

## iOS WKWebView 离线方案

### 1. 请求拦截

```swift
class OfflineWebViewHandler: NSObject, WKURLSchemeHandler {

    private let offlineDir: URL
    private let memoryCache = NSCache<NSString, WKWebResourceResponse>()

    func webView(
        _ webView: WKWebView,
        start urlSchemeTask: WKURLSchemeTask
    ) {
        guard let url = urlSchemeTask.request.url else {
            urlSchemeTask.cancel()
            return
        }

        // 检查内存缓存
        if let cached = memoryCache.object(forKey: url.absoluteString as NSString) {
            urlSchemeTask.didReceive(cached)
            urlSchemeTask.didFinish()
            return
        }

        // 解析资源路径
        guard let relativePath = parseResourcePath(url) else {
            urlSchemeTask.cancel()
            return
        }

        // 检查本地文件
        let localFile = offlineDir.appendingPathComponent(relativePath)
        if FileManager.default.fileExists(atPath: localFile.path) {
            do {
                let data = try Data(contentsOf: localFile)
                let mimeType = getMimeType(localFile.pathExtension)
                let response = WKWebResourceResponse(
                    data: data,
                    mimeType: mimeType,
                    expectedContentLength: data.count,
                    textEncodingName: "UTF-8"
                )

                memoryCache.setObject(response, forKey: url.absoluteString as NSString)
                urlSchemeTask.didReceive(response)
                urlSchemeTask.didFinish()
            } catch {
                urlSchemeTask.cancel()
            }
        } else {
            urlSchemeTask.cancel()
        }
    }

    func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) {
        // 清理资源
    }
}
```

### 2. 离线包安装

```swift
class OfflinePackageInstaller {

    private let offlineDir: URL

    func installPackage(_ packageInfo: PackageInfo) async throws {
        // 1. 下载 zip 包
        let zipURL = try await downloadPackage(packageInfo.downloadUrl)

        // 2. 创建临时目录
        let tempDir = offlineDir
            .deletingLastPathComponent()
            .appendingPathComponent("_offline_temp_\(packageInfo.version)")

        // 3. 解压
        try unzip(at: zipURL, to: tempDir)

        // 4. 原子性切换
        try atomicSwitch(to: tempDir)

        // 5. 清理旧版本
        try cleanupOldVersions(keep: packageInfo.version)
    }

    private func atomicSwitch(to newDir: URL) throws {
        let currentDir = offlineDir
        let backupDir = offlineDir
            .deletingLastPathComponent()
            .appendingPathComponent("_offline_backup")

        // 备份当前版本
        if FileManager.default.fileExists(atPath: currentDir.path) {
            try? FileManager.default.moveItem(at: currentDir, to: backupDir)
        }

        do {
            // 切换到新版本
            try FileManager.default.moveItem(at: newDir, to: currentDir)
            // 删除备份
            try? FileManager.default.removeItem(at: backupDir)
        } catch {
            // 失败则恢复
            try? FileManager.default.moveItem(at: backupDir, to: currentDir)
            throw error
        }
    }
}
```

## 预加载策略

```typescript
class OfflinePreloader {
    private packageManager: OfflinePackageManager;
    private networkDetector: NetworkDetector;

    async preloadForNextScreen(screenId: string): Promise<void> {
        const nextScreen = this.predictNextScreen(screenId);
        if (!nextScreen) return;

        const resources = this.getScreenResources(nextScreen);
        const criticalResources = resources.filter(r => r.priority === 'high');

        // WiFi 下预加载所有资源
        if (this.networkDetector.isWifi()) {
            await this.batchDownload(criticalResources);
        }
        // 4G 下只预加载关键资源
        else if (this.networkDetector.is4G()) {
            const critical = criticalResources.slice(0, 3);
            await this.batchDownload(critical);
        }
    }

    private predictNextScreen(currentScreen: string): string | null {
        const predictions = navigationGraph[currentScreen]?.likelyNext;
        if (!predictions) return null;
        return this.selectByProbability(predictions);
    }

    private async batchDownload(resources: Resource[]): Promise<void> {
        const downloads = resources.map(r => this.downloadResource(r));
        await Promise.all(downloads);
    }
}
```

## 缓存策略配置

```typescript
const CACHE_STRATEGY = {
    strategies: {
        // HTML 采用 SSR + 离线包
        'text/html': {
            source: ['offline', 'cdn'],
            cache: 'memory',
            ttl: 0
        },

        // 静态资源采用离线包优先
        'application/javascript': {
            source: ['offline', 'cdn'],
            cache: 'disk',
            ttl: 7 * 24 * 60 * 60
        },

        'text/css': {
            source: ['offline', 'cdn'],
            cache: 'disk',
            ttl: 7 * 24 * 60 * 60
        },

        // 图片采用 CDN + 内存缓存
        'image/*': {
            source: ['offline', 'cdn'],
            cache: 'memory',
            ttl: 24 * 60 * 60
        }
    }
};
```

## 增量更新

```kotlin
class IncrementalUpdater {

    suspend fun createDiff(
        oldPackage: File,
        newPackage: File
    ): DiffPackage {
        val operations = mutableListOf<FileOperation>()

        // 遍历新包中的文件
        for (newFile in newPackage.listFilesRecursively()) {
            val relativePath = newFile.relativeTo(newPackage)
            val oldFile = File(oldPackage, relativePath)

            when {
                !oldFile.exists() -> {
                    // 新增文件
                    operations.add(AddOperation(relativePath, newFile.readBytes()))
                }
                oldFile.checksum() != newFile.checksum() -> {
                    // 文件变更，使用 BSDiff
                    val patch = BSDiff.diff(oldFile.readBytes(), newFile.readBytes())
                    operations.add(PatchOperation(relativePath, patch))
                }
            }
        }

        // 处理删除的文件
        for (oldFile in oldPackage.listFilesRecursively()) {
            val relativePath = oldFile.relativeTo(oldPackage)
            val newFile = File(newPackage, relativePath)
            if (!newFile.exists()) {
                operations.add(DeleteOperation(relativePath))
            }
        }

        return DiffPackage(operations)
    }

    suspend fun applyDiff(
        oldPackage: File,
        diff: DiffPackage,
        outputDir: File
    ): File {
        outputDir.mkdirs()

        for (op in diff.operations) {
            when (op) {
                is AddOperation -> {
                    File(outputDir, op.path).writeBytes(op.data)
                }
                is PatchOperation -> {
                    val oldFile = File(oldPackage, op.path)
                    val newContent = BSDiff.patch(oldFile.readBytes(), op.patch)
                    File(outputDir, op.path).writeBytes(newContent)
                }
                is DeleteOperation -> {
                    File(outputDir, op.path).delete()
                }
            }
        }

        return outputDir
    }
}
```
