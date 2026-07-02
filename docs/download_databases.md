# ABI 全量数据库手动下载指南

> **目标路径**: `/root/autodl-tmp/resources/autoplasm`
> **总大小**: ~250GB（含 bakta full 84GB）
> **建议**: 开 3-4 个终端，按组并行执行

---

## 前置检查

```bash
# 确认所有 conda 环境已安装
ls /root/autodl-tmp/.mamba/envs/ | wc -l   # 应为 18

# 确认磁盘空间 (需 >300GB)
df -h /root/autodl-tmp

# 确认 aria2c (Kraken2 高速下载)
/root/autodl-tmp/.mamba/envs/autoplasm-base/bin/aria2c --version

# 确认资源根目录
mkdir -p /root/autodl-tmp/resources/autoplasm

# 设置常用快捷变量
export RES=/root/autodl-tmp/resources/autoplasm
export MAMBA=/root/autodl-tmp/.mamba
export ANN=$MAMBA/envs/autoplasm-annotation/bin
export DETECT=$MAMBA/envs/autoplasm-plasmid-detect/bin
export STATS=$MAMBA/envs/stats/bin
export EASYMETA=$MAMBA/envs/easymeta-p0/bin
export HUMANN=$MAMBA/envs/easymeta-humann/bin
```

---

## 第 0 步：修复已存在的半成品

> 一次性运行，无需并行

```bash
# 0a. mob_suite — 已有 2.3GB 完整数据，迁移即可
rm -rf $RES/mob_suite
mv /root/autodl-tmp/abi/MOB_SUITE_DB_NOT_CONFIGURED $RES/mob_suite
rm -f $RES/mob_suite/.lock
echo "✔ mob_suite: $(du -sh $RES/mob_suite | cut -f1)"

# 0b. plasmidfinder — 已 git clone，运行 INSTALL.py
rm -rf $RES/plasmidfinder_db
mv /root/autodl-tmp/abi/PLASMIDFINDER_DB_NOT_CONFIGURED $RES/plasmidfinder_db
$ANN/python $RES/plasmidfinder_db/INSTALL.py $ANN/kma_index
echo "✔ plasmidfinder 完成"

# 0c. bakta — 解压已下载的 2.9GB db.tar.xz
BAKTA_TAR=/root/autodl-tmp/abi/BAKTA_DB_NOT_CONFIGURED/db.tar.xz
if [ -f "$BAKTA_TAR" ] && [ $(stat -c%s "$BAKTA_TAR") -gt 1000000000 ]; then
    rm -rf $RES/bakta && mkdir -p $RES/bakta
    echo "解压 bakta (需几分钟)..."
    xz -d < "$BAKTA_TAR" | tar x -C $RES/bakta
    if [ -f $RES/bakta/bakta.db ]; then
        rm -f "$BAKTA_TAR"  # 释放 2.9GB
        echo "✔ bakta 解压完成: $(du -sh $RES/bakta | cut -f1)"
    else
        echo "✘ bakta 解压失败，请用第 3 组重新下载"
    fi
fi
```

---

## 第 1 组：小型数据库（4 终端并行，共 ~1.5GB）

### 终端 1: CheckM2 (~400MB)

```bash
PATH=$STATS:$PATH CHECKM2DB=$RES/checkm2 \
  checkm2 download --path $RES/checkm2
echo "✔ checkm2: $(du -sh $RES/checkm2 2>/dev/null | cut -f1)"
```

### 终端 2: RDP SINTAX Taxonomy (~50MB)

```bash
mkdir -p $RES/amplicon_taxonomy
wget -O $RES/amplicon_taxonomy/rdp_16s_v16_sp.fa.gz \
  https://www.drive5.com/sintax/rdp_16s_v16_sp.fa.gz
gunzip $RES/amplicon_taxonomy/rdp_16s_v16_sp.fa.gz
echo "✔ RDP: $(du -sh $RES/amplicon_taxonomy/rdp_16s_v16.fa | cut -f1)"
```

### 终端 3: AMRFinderPlus (~251MB)

```bash
PATH=$ANN:$PATH amrfinder_update -d $RES/amrfinderplus

# Post: 构建 BLAST 蛋白索引
AMRPROT=$(find $RES/amrfinderplus -name 'AMRProt.fa' 2>/dev/null | head -1)
if [ -n "$AMRPROT" ]; then
    $ANN/makeblastdb -in "$AMRPROT" -dbtype prot -out "$AMRPROT"
fi
echo "✔ amrfinderplus: $(du -sh $RES/amrfinderplus 2>/dev/null | cut -f1)"
```

### 终端 4: ABRicate (card / resfinder / vfdb / plasmidfinder)

```bash
mkdir -p $RES/abricate
PERL=$ANN/perl ABRICATE_DB=$ANN/abricate-get_db
for db in card resfinder vfdb plasmidfinder; do
    echo "  ▸ abricate: $db..."
    $PERL $ABRICATE_DB --dbdir $RES/abricate --db $db --force
done
echo "✔ abricate: $(du -sh $RES/abricate 2>/dev/null | cut -f1)"
```

---

## 第 2 组：中型数据库（2 终端并行，共 ~6GB）

### 终端 1: geNomad (~2.9GB)

```bash
PATH=$DETECT:$PATH genomad download-database $RES/genomad
echo "✔ genomad: $(du -sh $RES/genomad 2>/dev/null | cut -f1)"
```

### 终端 2: mob_suite (~3GB)

```bash
# 如果第 0 步已迁移则跳过
if [ ! -f $RES/mob_suite/ncbi_plasmid_full_seqs.fas.nhr ]; then
    PATH=$ANN:$PATH mob_init --database_directory $RES/mob_suite
fi
echo "✔ mob_suite: $(du -sh $RES/mob_suite 2>/dev/null | cut -f1)"
```

### 可选：工具安装（可并行）

```bash
# PLASMe
git clone --depth 1 https://github.com/ccb-hms/PLASMe.git $RES/PLASMe
cd $RES/PLASMe && $DETECT/pip install -e . --quiet

# Platon
git clone --depth 1 https://github.com/oschwengers/platon.git $RES/platon
cd $RES/platon && $DETECT/pip install -e . --quiet

# PlasX
git clone --depth 1 https://github.com/michaelgoldman/PlasX.git $RES/PlasX
cd $RES/PlasX && $DETECT/pip install -e . --quiet
```

---

## 第 3 组：大型数据库 ⚠️ 3 终端并行，共 ~168GB，耗时最长

### 终端 1: Bakta FULL (~84GB 解压后 / ~30GB 压缩下载)

```bash
# 如果第 0 步解压成功则跳过
if [ ! -f $RES/bakta/bakta.db ]; then
    PATH=$ANN:$PATH bakta_db download --output $RES/bakta --type full
fi
echo "✔ bakta: $(du -sh $RES/bakta 2>/dev/null | cut -f1)"
```

### 终端 2: MetaPhlAn v4 (~34GB)

```bash
PATH=$STATS:$PATH metaphlan --install --bowtie2db $RES/metaphlan --nproc 8
echo "✔ metaphlan: $(du -sh $RES/metaphlan 2>/dev/null | cut -f1)"
```

### 终端 3: Kraken2 Standard (~50GB, aria2c 8 线程并行)

```bash
ARIA2C=$MAMBA/envs/autoplasm-base/bin/aria2c
URL=https://genome-idx.s3.amazonaws.com/kraken/k2_standard_20260226.tar.gz
TAR=$RES/kraken2.tar.gz.part
STAGE=$RES/kraken2.staging
DEST=$RES/kraken2

# 原子下载 → 解压 → 交换
rm -f $TAR && rm -rf $STAGE $DEST
$ARIA2C -x 8 -s 8 --continue=true --max-tries=3 --retry-wait=5 \
  -d $RES -o kraken2.tar.gz.part "$URL"
echo "解压中..."
mkdir -p $STAGE && tar xzf $TAR -C $STAGE
mv $STAGE $DEST && rm -f $TAR
echo "✔ kraken2: $(du -sh $DEST | cut -f1)"
```

---

## 第 4 组：GTDB-Tk + eggNOG（2 终端并行，共 ~60GB）

### 终端 1: GTDB-Tk (~30GB)

```bash
PATH=$STATS:$PATH GTDBTK_DATA_PATH=$RES/gtdbtk gtdbtk db download
echo "✔ gtdbtk: $(du -sh $RES/gtdbtk 2>/dev/null | cut -f1)"
```

### 终端 2: eggNOG-mapper (~30GB)

```bash
PATH=$ANN:$PATH download_eggnog_data.py -y --data_dir $RES/eggnog_mapper
echo "✔ eggnog: $(du -sh $RES/eggnog_mapper 2>/dev/null | cut -f1)"
```

---

## 第 5 组：easyMetagenome（3 终端并行，共 ~11GB）

### 终端 1: KneadData 宿主基因组 (~3GB)

```bash
PATH=$EASYMETA:$PATH \
  kneaddata_database --download human_genome bowtie2 $RES/kneaddata_host
echo "✔ kneaddata: $(du -sh $RES/kneaddata_host 2>/dev/null | cut -f1)"
```

### 终端 2: HUMAnN ChocoPhlAn (~5GB)

```bash
PATH=$HUMANN:$PATH \
  humann_databases --download chocophlan full $RES/humann/chocophlan
echo "✔ chocophlan: $(du -sh $RES/humann/chocophlan 2>/dev/null | cut -f1)"
```

### 终端 3: HUMAnN UniRef90 (~3GB)

```bash
PATH=$HUMANN:$PATH \
  humann_databases --download uniref uniref90_diamond $RES/humann/uniref
echo "✔ uniref: $(du -sh $RES/humann/uniref 2>/dev/null | cut -f1)"
```

---

## 第 6 步：CARD / RGI

```bash
PATH=$ANN:$PATH rgi load --card_json $RES/card/card.json --local
# 如果失败 → 手动从 https://card.mcmaster.ca/download 下载
```

---

## 进度监控

随时在新终端运行：

```bash
bash /root/autodl-tmp/abi/scripts/cloud/monitor_downloads.sh
```

## 汇总验证

全部下载完成后：

```bash
echo "=== 资源目录 ===" && du -sh /root/autodl-tmp/resources/autoplasm/*/ && \
echo "" && echo "=== 磁盘 ===" && df -h /root/autodl-tmp && \
echo "" && echo "=== 数据库清单 ===" && \
for d in genomad bakta mob_suite plasmidfinder_db metaphlan amrfinderplus kraken2 gtdbtk checkm2 eggnog_mapper abricate amplicon_taxonomy card kneaddata_host humann/chocophlan humann/uniref; do
    p=/root/autodl-tmp/resources/autoplasm/$d
    if [ -d "$p" ] || [ -f "$p" ]; then
        printf "  %-25s %8s\n" "$d" "$(du -sh "$p" 2>/dev/null | cut -f1)"
    else
        printf "  %-25s %8s\n" "$d" "MISSING"
    fi
done
```

---

## 数据库总览

| 序号 | 数据库 | 大小 | 所属插件 | 下载方式 |
|:---:|:---|---:|---|:---|
| 1 | **genomad** | 2.9 GB | metagenomic_plasmid | `genomad download-database` |
| 2 | **bakta** (full) | 84 GB | metagenomic_plasmid | `bakta_db download --type full` |
| 3 | **mob_suite** | 3.0 GB | metagenomic_plasmid | `mob_init` |
| 4 | **plasmidfinder** | <1 MB | metagenomic_plasmid | `git clone` + `INSTALL.py` |
| 5 | **metaphlan** | 34 GB | metagenomic_plasmid / easymetagenome | `metaphlan --install` |
| 6 | **amrfinderplus** | 251 MB | metagenomic_plasmid / wgs_bacteria | `amrfinder_update -d` |
| 7 | **kraken2** | 50 GB | metagenomic_plasmid / easymetagenome | aria2c + tar |
| 8 | **gtdbtk** | 30 GB | metagenomic_plasmid | `gtdbtk db download` |
| 9 | **checkm2** | ~400 MB | metagenomic_plasmid | `checkm2 download` |
| 10 | **eggnog_mapper** | 30 GB | metagenomic_plasmid | `download_eggnog_data.py` |
| 11 | **abricate** | ~100 MB | metagenomic_plasmid | `abricate-get_db` |
| 12 | **RDP taxonomy** | 50 MB | amplicon_16s | `wget` |
| 13 | **CARD (RGI)** | ~1 GB | metagenomic_plasmid | `rgi load` |
| 14 | **kneaddata host** | 3 GB | easymetagenome | `kneaddata_database` |
| 15 | **HUMAnN chocophlan** | 5 GB | easymetagenome | `humann_databases` |
| 16 | **HUMAnN uniref** | 3 GB | easymetagenome | `humann_databases` |
| | **合计** | **~250 GB** | | |

---

## 最优执行策略

```
终端1: 第0步 → 第1组(顺序) → 第3组(bakta)     → 第4组(gtdbtk)
终端2:              → 第2组       → 第3组(metaphlan) → 第4组(eggnog)
终端3:              →             → 第3组(kraken2)   → 第5组(全部)
终端4:              → 第1组(部分) →                    → 第6步
```

> **预计总耗时**: 3-10 小时（取决于网络带宽）
