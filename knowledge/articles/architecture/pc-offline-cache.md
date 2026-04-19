# PC 客户端离线包缓存与增量更新系统

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Update Server                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Version DB │  │ Package CDN │  │  Diff Tool  │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      PC Client                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │UpdateManager│  │CacheManager │  │ VersionMgr  │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                          │                                  │
│  ┌─────────────────────────────────────────────────┐      │
│  │              Local Package Store                 │      │
│  │  /packages/                                      │      │
│  │    └── v1.2.0/                                   │      │
│  │         ├── index.html                           │      │
│  │         ├── static/                              │      │
│  │         └── manifest.json                        │      │
│  └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## 核心数据结构

### manifest.json - 包清单文件

```typescript
interface PackageManifest {
  version: string;           // 包版本号
  name: string;             // 包名称
  buildTime: number;        // 构建时间戳
  checksum: string;         // 完整包校验和
  files: PackageFile[];     // 文件列表
  entry: string;           // 入口文件
}

interface PackageFile {
  path: string;             // 文件路径
  size: number;             // 文件大小
  checksum: string;         // 文件校验和 (SHA256)
  compressed?: boolean;       // 是否压缩
}
```

### version.json - 版本信息

```typescript
interface VersionInfo {
  latest: string;           // 最新版本
  mandatory: boolean;       // 是否强制更新
  releaseNotes: string;     // 更新说明
  packages: PackageInfo[];  // 可用包列表
}

interface PackageInfo {
  version: string;
  size: number;
  downloadUrl: string;
  checksum: string;
  fromVersion?: string;     // 增量更新起始版本
  diffSize?: number;        // 增量包大小
}
```

## 版本管理器实现

```typescript
class VersionManager {
  private readonly VERSION_KEY = 'local_version';
  private readonly BASE_PATH: string;

  constructor(basePath: string) {
    this.BASE_PATH = basePath;
  }

  async getCurrentVersion(): Promise<string> {
    const manifest = await this.readManifest();
    return manifest?.version || '0.0.0';
  }

  async checkForUpdates(): Promise<UpdateInfo | null> {
    const currentVersion = await this.getCurrentVersion();
    const serverInfo = await this.fetchServerVersion();

    if (this.shouldUpdate(currentVersion, serverInfo.latest)) {
      return this.calculateUpdatePath(currentVersion, serverInfo.latest);
    }
    return null;
  }

  private shouldUpdate(current: string, latest: string): boolean {
    return this.compareVersions(current, latest) < 0;
  }

  private compareVersions(v1: string, v2: string): number {
    const parts1 = v1.split('.').map(Number);
    const parts2 = v2.split('.').map(Number);

    for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
      const p1 = parts1[i] || 0;
      const p2 = parts2[i] || 0;
      if (p1 !== p2) return p1 - p2;
    }
    return 0;
  }

  private calculateUpdatePath(
    from: string,
    to: string
  ): UpdateInfo {
    const diffPackages = this.findDiffPackages(from, to);
    const fullPackage = this.getFullPackage(to);

    if (diffPackages && diffPackages.size < fullPackage.size * 0.5) {
      return {
        type: 'incremental',
        package: diffPackages
      };
    }

    return {
      type: 'full',
      package: fullPackage
    };
  }
}
```

## 缓存管理器实现

```typescript
class CacheManager {
  private cachePath: string;
  private maxCacheSize: number = 1024 * 1024 * 1024; // 1GB
  private versionManager: VersionManager;

  async initialize(): Promise<void> {
    await this.ensureDirectory(this.cachePath);
    await this.cleanOldVersions();
  }

  async cachePackage(packageInfo: PackageInfo): Promise<void> {
    const packagePath = path.join(this.cachePath, packageInfo.version);

    // 下载包
    const zipPath = await this.downloadPackage(packageInfo);

    // 校验完整性
    await this.verifyChecksum(zipPath, packageInfo.checksum);

    // 解压到版本目录
    await this.extractPackage(zipPath, packagePath);

    // 清理 zip
    await fs.remove(zipPath);

    // 更新当前版本指向
    await this.setCurrentVersion(packageInfo.version);
  }

  async getCachedPackage(version: string): Promise<string | null> {
    const packagePath = path.join(this.cachePath, version);
    const manifestPath = path.join(packagePath, 'manifest.json');

    if (await fs.pathExists(manifestPath)) {
      return packagePath;
    }
    return null;
  }

  private async cleanOldVersions(): Promise<void> {
    const entries = await fs.readdir(this.cachePath);
    const versionDirs = entries.filter(e => semver.valid(e));

    const toKeep = new Set<string>();
    const current = await this.versionManager.getCurrentVersion();
    toKeep.add(current);

    for (const dir of versionDirs) {
      const size = await this.getDirSize(path.join(this.cachePath, dir));
      if (this.calculateTotalSize() + size > this.maxCacheSize) {
        await fs.remove(path.join(this.cachePath, dir));
      }
    }
  }
}
```

## 增量更新算法

```typescript
class IncrementalUpdate {
  async createDiff(
    oldPackage: string,
    newPackage: string,
    outputPath: string
  ): Promise<void> {
    const oldManifest = await this.readManifest(oldPackage);
    const newManifest = await this.readManifest(newPackage);

    const diff: DiffPackage = {
      version: newManifest.version,
      fromVersion: oldManifest.version,
      operations: []
    };

    for (const newFile of newManifest.files) {
      const oldFile = oldManifest.files.find(f => f.path === newFile.path);

      if (!oldFile) {
        diff.operations.push({
          type: 'add',
          path: newFile.path,
          data: await this.readFile(path.join(newPackage, newFile.path))
        });
      } else if (oldFile.checksum !== newFile.checksum) {
        const oldData = await this.readFile(path.join(oldPackage, oldFile.path));
        const newData = await this.readFile(path.join(newPackage, newFile.path));
        const patch = bsdiff.create(oldData, newData);

        diff.operations.push({
          type: 'patch',
          path: newFile.path,
          patch,
          size: patch.length
        });
      }
    }

    for (const oldFile of oldManifest.files) {
      if (!newManifest.files.find(f => f.path === oldFile.path)) {
        diff.operations.push({
          type: 'delete',
          path: oldFile.path
        });
      }
    }

    await this.writeDiffPackage(diff, outputPath);
  }

  async applyDiff(
    oldPackage: string,
    diffPath: string,
    outputPath: string
  ): Promise<void> {
    const diff = await this.readDiffPackage(diffPath);

    await fs.mkdir(outputPath, { recursive: true });

    for (const op of diff.operations) {
      switch (op.type) {
        case 'add':
          await this.writeFile(path.join(outputPath, op.path), op.data);
          break;

        case 'patch':
          const oldData = await this.readFile(path.join(oldPackage, op.path));
          const newData = bspatch.apply(oldData, op.patch);
          await this.writeFile(path.join(outputPath, op.path), newData);
          break;

        case 'delete':
          await fs.remove(path.join(outputPath, op.path));
          break;
      }
    }
  }
}
```

## Electron 实现示例

```typescript
import { app, ipcMain } from 'electron';
import * as path from 'path';
import * as fs from 'fs-extra';

class ElectronUpdater {
  private cacheDir: string;
  private versionManager: VersionManager;
  private cacheManager: CacheManager;

  constructor() {
    this.cacheDir = path.join(app.getPath('userData'), 'packages');
    this.versionManager = new VersionManager(this.cacheDir);
    this.cacheManager = new CacheManager(this.cacheDir);
  }

  async checkForUpdates(): Promise<UpdateInfo | null> {
    return this.versionManager.checkForUpdates();
  }

  async downloadAndInstall(info: UpdateInfo): Promise<void> {
    // 1. 下载更新包
    await this.cacheManager.cachePackage(info.package);

    // 2. 备份当前版本
    const currentVersion = await this.versionManager.getCurrentVersion();
    const backupDir = path.join(this.cacheDir, '_backup');
    await fs.copy(
      path.join(this.cacheDir, currentVersion),
      backupDir
    );

    // 3. 安装新版本
    await this.installVersion(info.package.version);

    // 4. 通知渲染进程
    ipcMain.emit('update-downloaded');
  }

  async installVersion(version: string): Promise<void> {
    const packagePath = path.join(this.cacheDir, version);
    const appDir = app.getAppPath();

    // 原子性切换
    const tempDir = path.join(this.cacheDir, `_installing_${version}`);
    await fs.copy(packagePath, tempDir);
    await fs.remove(appDir);
    await fs.move(tempDir, appDir);
  }
}
```

## 差分算法对比

| 算法 | 压缩率 | 速度 | 内存占用 | 适用场景 |
|------|--------|------|----------|----------|
| BSDiff | 最高 | 慢 | 高 | 大文件差异 |
| Bsdiff4j | 高 | 中 | 中 | Android |
| HDiffPatch | 高 | 快 | 低 | 通用 |
| Courgette | 中 | 快 | 低 | 文本文件 |

## 回滚机制

```typescript
class RollbackManager {
  async rollback(version: string): Promise<void> {
    const backupDir = path.join(this.cacheDir, '_backup');
    const currentDir = this.getCurrentPackageDir();

    // 备份当前版本到临时目录
    const tempDir = path.join(this.cacheDir, `_rollback_temp`);
    await fs.copy(currentDir, tempDir);

    try {
      // 恢复到指定版本
      await fs.copy(path.join(this.cacheDir, version), currentDir);
      await this.versionManager.setCurrentVersion(version);
    } catch (error) {
      // 恢复失败，回滚到临时目录的内容
      await fs.copy(tempDir, currentDir);
      await fs.remove(tempDir);
      throw error;
    }
  }
}
```

## 离线包加载策略

```typescript
class OfflineLoader {
  private cacheManager: CacheManager;
  private versionManager: VersionManager;

  async loadResource(reqPath: string): Promise<string | null> {
    const version = await this.versionManager.getCurrentVersion();
    const cachedPath = await this.cacheManager.getCachedPackage(version);

    if (cachedPath) {
      const fullPath = path.join(cachedPath, reqPath);
      if (await fs.pathExists(fullPath)) {
        return await fs.readFile(fullPath, 'utf-8');
      }
    }

    return null;
  }

  async preloadCriticalResources(): Promise<void> {
    const criticalPaths = [
      'index.html',
      'static/js/main.js',
      'static/css/main.css'
    ];

    await Promise.all(
      criticalPaths.map(p => this.loadResource(p))
    );
  }
}
```
