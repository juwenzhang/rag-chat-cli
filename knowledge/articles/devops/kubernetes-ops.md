# Kubernetes 集群运维实战指南

## 前言

Kubernetes 已成为容器编排的事实标准。本文将从集群部署、应用管理、监控告警、灾难恢复等维度，深入探讨 K8s 生产环境的运维实践。

## 一、集群架构

### 1.1 高可用集群拓扑

```
┌─────────────────────────────────────────────────────────────────┐
│                         Load Balancer                            │
│                    (云厂商 SLB / MetalLB)                        │
└─────────────────────┬─────────────────────┬─────────────────────┘
                      │                     │
        ┌─────────────┴───────┐ ┌────────────┴─────────┐
        │   Control Plane 1   │ │   Control Plane 2    │
        │  ┌───────────────┐  │ │  ┌───────────────┐   │
        │  │ kube-apiserver│  │ │  │ kube-apiserver│   │
        │  │ kube-scheduler│  │ │  │ kube-scheduler│   │
        │  │ kube-controller│ │ │  │ kube-controller│  │
        │  │    etcd        │ │ │  │    etcd        │   │
        │  └───────────────┘  │ │  └───────────────┘   │
        └────────────────────┘ └───────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────────┐
        │                   Worker Nodes                  │
        │  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
        │  │ Node 1  │  │ Node 2  │  │ Node 3  │        │
        │  │Pod  Pod │  │Pod  Pod │  │Pod  Pod │        │
        │  └─────────┘  └─────────┘  └─────────┘        │
        └───────────────────────────────────────────────┘
```

### 1.2 集群组件

```yaml
# kube-apiserver 高可用配置
apiVersion: v1
kind: Pod
metadata:
  name: kube-apiserver
  namespace: kube-system
spec:
  containers:
    - name: kube-apiserver
      image: k8s.gcr.io/kube-apiserver:v1.28.0
      command:
        - kube-apiserver
        - --etcd-servers=https://etcd-1:2379,https://etcd-2:2379,https://etcd-3:2379
        - --service-cluster-ip-range=10.96.0.0/12
        - --feature-gates=TTLAfterFinished=true
        - --runtime-config=admissionregistration.k8s.io/v1
        - --enable-admission-plugins=NodeRestriction
        - --audit-log-maxage=30
        - --audit-log-maxBackup=10
        - --audit-log-maxSize=100
        - --audit-log-path=/var/log/audit.log
```

## 二、应用管理

### 2.1 Deployment 策略

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: production
  labels:
    app: myapp
    version: v1.0.0
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
        version: v1.0.0
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app
                      operator: In
                      values:
                        - myapp
                topologyKey: kubernetes.io/hostname
      containers:
        - name: myapp
          image: myapp:v1.0.0
          ports:
            - containerPort: 8080
              name: http
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 3
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 10"]
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: POD_IP
              valueFrom:
                fieldRef:
                  fieldPath: status.podIP
```

### 2.2 HPA 自动扩缩容

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 4
          periodSeconds: 15
      selectPolicy: Max
```

## 三、存储管理

### 3.1 PV 和 PVC

```yaml
# persistent-volume.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-data
  labels:
    type: local
spec:
  capacity:
    storage: 100Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: local-storage
  local:
    path: /data/pv
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values:
                - node-1

---
# persistent-volume-claim.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-data
  namespace: production
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
  storageClassName: local-storage
  selector:
    matchLabels:
      type: local
```

### 3.2 StatefulSet

```yaml
# statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mysql
  namespace: production
spec:
  serviceName: mysql
  replicas: 3
  selector:
    matchLabels:
      app: mysql
  template:
    metadata:
      labels:
        app: mysql
    spec:
      initContainers:
        - name: init-mysql
          image: mysql:8.0
          command:
            - bash
            - "-c"
            - |
              set -ex
              [[ $HOSTNAME =~ -(0|1|2)$ ]] || exit 1
              ordinal=${HOSTNAME##*-}
              echo [mysqld] > /mnt/config-map/master.cnf
              [[ $ordinal == "0" ]] && echo [mysqld] >> /mnt/config-map/master.cnf
              if [[ $ordinal != "0" ]]; then
                echo server-id=$((100 + $ordinal)) >> /mnt/config-map/master.cnf
                echo log-bin=mysql-bin >> /mnt/config-map/master.cnf
              fi
          volumeMounts:
            - name: config
              mountPath: /mnt/config-map
      containers:
        - name: mysql
          image: mysql:8.0
          ports:
            - name: mysql
              containerPort: 3306
          volumeMounts:
            - name: data
              mountPath: /var/lib/mysql
              subPath: mysql
            - name: config
              mountPath: /etc/mysql/conf.d
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
          env:
            - name: MYSQL_ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: mysql-secret
                  key: root-password
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: "standard"
        resources:
          requests:
            storage: 10Gi
```

## 四、监控告警

### 4.1 Prometheus 配置

```yaml
# prometheus-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
      evaluation_interval: 15s

    alerting:
      alertmanagers:
        - static_configs:
            - targets:
                - alertmanager:9093

    rule_files:
      - /etc/prometheus/rules/*.yml

    scrape_configs:
      - job_name: 'kubernetes-apiservers'
        kubernetes_sd_configs:
          - role: endpoints
        scheme: https
        tls_config:
          ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
        bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
        relabel_configs:
          - source_labels: [__meta_kubernetes_namespace, __meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
            action: keep
            regex: default;kubernetes;https

      - job_name: 'kubernetes-nodes'
        kubernetes_sd_configs:
          - role: node
        relabel_configs:
          - action: labelmap
            regex: __meta_kubernetes_node_label_(.+)
          - target_label: __address__
            replacement: kubernetes.default.svc:443
          - source_labels: [__meta_kubernetes_node_name]
            regex: (.+)
            target_label: __metrics_path__
            replacement: /api/v1/nodes/${1}/proxy/metrics

      - job_name: 'myapp'
        kubernetes_sd_configs:
          - role: pod
        relabel_configs:
          - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
            action: keep
            regex: true
          - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
            action: replace
            target_label: __metrics_path__
            regex: (.+)
            replacement: ${1}
          - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
            action: replace
            regex: ([^:]+)(?::\d+)?;(\d+)
            replacement: $1:$2
            target_label: __address__
```

### 4.2 告警规则

```yaml
# alert-rules.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: myapp-alerts
  namespace: monitoring
spec:
  groups:
    - name: myapp
      rules:
        - alert: HighErrorRate
          expr: |
            sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
            / sum(rate(http_requests_total[5m])) by (service) > 0.05
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "High error rate detected"
            description: "Service {{ $labels.service }} has error rate > 5%"

        - alert: HighLatency
          expr: |
            histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service)) > 2
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "High latency detected"
            description: "Service {{ $labels.service }} P99 latency > 2s"

        - alert: PodMemoryUsageHigh
          expr: |
            (sum(container_memory_working_set_bytes{container!=""}) by (pod)
            / sum(container_spec_memory_limit_bytes{container!=""}) by (pod)) > 0.9
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Pod memory usage high"
            description: "Pod {{ $labels.pod }} memory usage > 90%"
```

## 五、灾难恢复

### 5.1 etcd 备份

```bash
#!/bin/bash
# backup-etcd.sh

ETCD_ENDPOINT="https://127.0.0.1:2379"
BACKUP_DIR="/backup/etcd"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="etcd-snapshot-${TIMESTAMP}"

# 创建备份目录
mkdir -p ${BACKUP_DIR}

# 执行快照
ETCDCTL_API=3 etcdctl \
    --endpoints=${ETCD_ENDPOINT} \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key \
    snapshot save ${BACKUP_DIR}/${BACKUP_FILE}

# 压缩备份
gzip ${BACKUP_DIR}/${BACKUP_FILE}

# 保留最近 7 天的备份
find ${BACKUP_DIR} -name "etcd-snapshot-*.db.gz" -mtime +7 -delete

echo "Backup completed: ${BACKUP_FILE}.gz"
```

### 5.2 恢复流程

```bash
#!/bin/bash
# restore-etcd.sh

BACKUP_FILE=$1
ETCD_ENDPOINT="https://127.0.0.1:2379"

# 停止 kube-apiserver
kubectl delete pod -n kube-system -l component=kube-apiserver

# 恢复数据
ETCDCTL_API=3 etcdctl \
    --endpoints=${ETCD_ENDPOINT} \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key \
    snapshot restore ${BACKUP_FILE} \
    --data-dir=/var/lib/etcd/restore

# 重启 etcd
systemctl restart etcd

# 重启 kube-apiserver
kubectl get pods -n kube-system -l component=kube-apiserver
```

## 总结

Kubernetes 生产运维要点：
1. **高可用架构**：多 Control Plane 部署、etcd 集群
2. **应用管理**：合理的探针配置、自动扩缩容策略
3. **存储管理**：PV/PVC 持久化、StatefulSet 有状态应用
4. **监控告警**：Prometheus + Grafana 监控体系
5. **灾难恢复**：定期 etcd 备份、恢复演练