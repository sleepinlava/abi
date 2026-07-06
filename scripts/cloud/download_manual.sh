#!/usr/bin/env bash
# =============================================================================
# ABI 数据库手动下载 — 分阶段执行，每个阶段可独立运行
# 目标路径: /root/autodl-tmp/resources/autoplasm
# =============================================================================
set -euo pipefail

# ── 路径常量 ──
export MAMBA=/root/autodl-tmp/.mamba
export RES=/root/autodl-tmp/resources/autoplasm
mkdir -p $RES

# ── 便捷 alias: env bin 目录 ──
ANNOTATION=$MAMBA/envs/autoplasm-annotation/bin
PLASMID_DETECT=$MAMBA/envs/autoplasm-plasmid-detect/bin
STATS=$MAMBA/envs/stats/bin
BASE=$MAMBA/envs/autoplasm-base/bin
EASYMETA_P0=$MAMBA/envs/easymeta-p0/bin
EASYMETA_HUMANN=$MAMBA/envs/easymeta-humann/bin
CONDA_PERL=$ANNOTATION/perl

# ================================================================
# Phase 0: 修复已存在的半成品
# ================================================================
echo "=== Phase 0: 修复半成品 ==="

# 0a. mob_suite — 数据完整，只需移除 .lock
if [ -d /root/autodl-tmp/abi/MOB_SUITE_DB_NOT_CONFIGURED ] && \
   [ -f /root/autodl-tmp/abi/MOB_SUITE_DB_NOT_CONFIGURED/ncbi_plasmid_full_seqs.fas.nhr ]; then
    rm -rf $RES/mob_suite
    mv /root/autodl-tmp/abi/MOB_SUITE_DB_NOT_CONFIGURED $RES/mob_suite
    rm -f $RES/mob_suite/.lock
    touch $RES/mob_suite/.autoplasm_resource_ready
    echo "  ✔ mob_suite 迁移完成"
fi

# 0b. plasmidfinder — 已 git clone, 运行 INSTALL.py
if [ -d /root/autodl-tmp/abi/PLASMIDFINDER_DB_NOT_CONFIGURED/.git ]; then
    rm -rf $RES/plasmidfinder_db
    mv /root/autodl-tmp/abi/PLASMIDFINDER_DB_NOT_CONFIGURED $RES/plasmidfinder_db
    $ANNOTATION/python $RES/plasmidfinder_db/INSTALL.py $ANNOTATION/kma_index
    touch $RES/plasmidfinder_db/.autoplasm_resource_ready
    echo "  ✔ plasmidfinder 迁移完成"
fi

# 0c. bakta — 解压 db.tar.xz (如果存在)
if [ -f /root/autodl-tmp/abi/BAKTA_DB_NOT_CONFIGURED/db.tar.xz ] && \
   [ $(stat -c%s /root/autodl-tmp/abi/BAKTA_DB_NOT_CONFIGURED/db.tar.xz) -gt 1000000000 ]; then
    rm -rf $RES/bakta
    mkdir -p $RES/bakta
    echo "  解压 bakta db.tar.xz (这需要几分钟)..."
    xz -d < /root/autodl-tmp/abi/BAKTA_DB_NOT_CONFIGURED/db.tar.xz | tar x -C $RES/bakta
    if [ -f $RES/bakta/bakta.db ]; then
        touch $RES/bakta/.autoplasm_resource_ready
        rm -f /root/autodl-tmp/abi/BAKTA_DB_NOT_CONFIGURED/db.tar.xz
        echo "  ✔ bakta 解压完成 ($(du -sh $RES/bakta | cut -f1))"
    else
        echo "  ✘ bakta 解压失败, 需要重新下载"
    fi
fi

# ================================================================
# Phase 1: 小型数据库 (可全部并行)
#   在多个终端分别运行这4个命令
# ================================================================
echo "=== Phase 1: 小型数据库 — 可开4个终端分别运行 ==="

cat << 'CMDS'
# ── 终端1: checkm2 (~400MB) ──
PATH=/root/autodl-tmp/.mamba/envs/stats/bin:$PATH \
CHECKM2DB=/root/autodl-tmp/resources/autoplasm/checkm2 \
checkm2 download --path /root/autodl-tmp/resources/autoplasm/checkm2

# ── 终端2: RDP SINTAX taxonomy (~50MB) ──
wget -O /root/autodl-tmp/resources/autoplasm/amplicon_taxonomy/rdp_16s_v16_sp.fa.gz \
  https://www.drive5.com/sintax/rdp_16s_v16_sp.fa.gz \
  && gunzip /root/autodl-tmp/resources/autoplasm/amplicon_taxonomy/rdp_16s_v16_sp.fa.gz

# ── 终端3: AMRFinderPlus (~251MB) ──
PATH=/root/autodl-tmp/.mamba/envs/autoplasm-annotation/bin:$PATH \
amrfinder_update -d /root/autodl-tmp/resources/autoplasm/amrfinderplus

# ── 终端4: ABRicate (card/resfinder/vfdb/plasmidfinder) ──
for db in card resfinder vfdb plasmidfinder; do
  /root/autodl-tmp/.mamba/envs/autoplasm-annotation/bin/perl \
    /root/autodl-tmp/.mamba/envs/autoplasm-annotation/bin/abricate-get_db \
    --dbdir /root/autodl-tmp/resources/autoplasm/abricate --db $db --force
done
CMDS

# ================================================================
# Phase 2: geNomad (~2.9GB) + mob_suite(~3GB)
# ================================================================
echo "=== Phase 2: genomad + mob_suite — 可分别在两个终端 ==="

cat << 'CMDS'
# ── 终端1: geNomad (~2.9GB) ──
PATH=/root/autodl-tmp/.mamba/envs/autoplasm-plasmid-detect/bin:$PATH \
genomad download-database /root/autodl-tmp/resources/autoplasm/genomad

# ── 终端2: mob_suite (~3GB) ──
PATH=/root/autodl-tmp/.mamba/envs/autoplasm-annotation/bin:$PATH \
mob_init --database_directory /root/autodl-tmp/resources/autoplasm/mob_suite
CMDS

# ================================================================
# Phase 3: 三大数据库 — bakta(84GB) / metaphlan(34GB) / kraken2(50GB)
# ================================================================
echo "=== Phase 3: 大型数据库 — 开3个终端并行 ==="

cat << 'CMDS'
# ── 终端1: Bakta FULL (~84GB 解压后) ──
PATH=/root/autodl-tmp/.mamba/envs/autoplasm-annotation/bin:$PATH \
bakta_db download --output /root/autodl-tmp/resources/autoplasm/bakta --type full

# ── 终端2: MetaPhlAn v4 (~34GB) ──
PATH=/root/autodl-tmp/.mamba/envs/stats/bin:$PATH \
metaphlan --install --bowtie2db /root/autodl-tmp/resources/autoplasm/metaphlan --nproc 8

# ── 终端3: Kraken2 Standard (~50GB, aria2c 8线并行) ──
# 先安装 aria2c:
#   mamba install -n autoplasm-base -c conda-forge aria2 -y
ARIA2C=/root/autodl-tmp/.mamba/envs/autoplasm-base/bin/aria2c
URL=https://genome-idx.s3.amazonaws.com/kraken/k2_standard_20260226.tar.gz
TAR=/root/autodl-tmp/resources/autoplasm/kraken2.tar.gz.part
STAGE=/root/autodl-tmp/resources/autoplasm/kraken2.staging
DEST=/root/autodl-tmp/resources/autoplasm/kraken2

rm -f $TAR && rm -rf $STAGE $DEST
$ARIA2C -x 8 -s 8 --continue=true --max-tries=3 --retry-wait=5 \
  -d /root/autodl-tmp/resources/autoplasm -o kraken2.tar.gz.part "$URL"
mkdir -p $STAGE
tar xzf $TAR -C $STAGE
mv $STAGE $DEST
rm -f $TAR
echo "Kraken2 完成: $(du -sh $DEST | cut -f1)"
CMDS

# ================================================================
# Phase 4: gtdbtk(30GB) + eggnog_mapper(30GB)
# ================================================================
echo "=== Phase 4: gtdbtk + eggnog — 开2个终端 ==="

cat << 'CMDS'
# ── 终端1: GTDB-Tk (~30GB) ──
PATH=/root/autodl-tmp/.mamba/envs/stats/bin:$PATH \
GTDBTK_DATA_PATH=/root/autodl-tmp/resources/autoplasm/gtdbtk \
gtdbtk db download

# ── 终端2: eggNOG-mapper (~30GB) ──
PATH=/root/autodl-tmp/.mamba/envs/autoplasm-annotation/bin:$PATH \
download_eggnog_data.py -y --data_dir /root/autodl-tmp/resources/autoplasm/eggnog_mapper
CMDS

# ================================================================
# Phase 5: easyMetagenome — kneaddata(3GB) + HUMAnN(8GB)
# ================================================================
echo "=== Phase 5: kneaddata + HUMAnN — 开3个终端 ==="

cat << 'CMDS'
# ── 终端1: KneadData human host (~3GB) ──
PATH=/root/autodl-tmp/.mamba/envs/easymeta-p0/bin:$PATH \
kneaddata_database --download human_genome bowtie2 \
  /root/autodl-tmp/resources/autoplasm/kneaddata_host

# ── 终端2: HUMAnN ChocoPhlAn (~5GB) ──
PATH=/root/autodl-tmp/.mamba/envs/easymeta-humann/bin:$PATH \
humann_databases --download chocophlan full \
  /root/autodl-tmp/resources/autoplasm/humann/chocophlan

# ── 终端3: HUMAnN UniRef90 (~3GB) ──
PATH=/root/autodl-tmp/.mamba/envs/easymeta-humann/bin:$PATH \
humann_databases --download uniref uniref90_diamond \
  /root/autodl-tmp/resources/autoplasm/humann/uniref
CMDS

# ================================================================
# Phase 6: CARD/RGI
# ================================================================
echo "=== Phase 6: CARD ==="

cat << 'CMDS'
# CARD/RGI 数据库 (需要网络)
PATH=/root/autodl-tmp/.mamba/envs/autoplasm-annotation/bin:$PATH \
rgi load --card_json /root/autodl-tmp/resources/autoplasm/card/card.json --local
# 如果失败 → 手动从 https://card.mcmaster.ca/download 下载
CMDS

echo ""
echo "===== 全部命令输出完毕 ====="
echo "数据库总计 ~250GB"
echo "建议: 开3个终端, 分别运行 Phase 1→2→3→4→5→6 的小型/中型/大型命令"
