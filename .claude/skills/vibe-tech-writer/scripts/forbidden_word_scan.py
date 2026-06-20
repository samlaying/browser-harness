#!/usr/bin/env python3
"""
扫描文章中的违禁词，输出命中列表和替换建议。
用法: python forbidden_word_scan.py <article_file.md>
"""

import sys
import re

FORBIDDEN_WORDS = [
    # 递进关系和逻辑词汇（42个）
    "然而", "此外", "总之", "因此", "综上所述", "例如", "基于此",
    "显而易见", "值得注意的是", "不可否认", "从某种程度上",
    "换句话说", "尽管如此", "由此可见", "因此可见",
    "不可避免地", "事实上", "显著",
    "在此基础上", "尤其是", "基于以上分析", "毫无疑问",
    "值得一提的是", "相较于", "可见", "因此可以推断",
    "进一步而言", "如上所述", "结合实际情况", "综合考虑",
    "在此过程中", "进一步分析", "在一定程度上", "相反",
    "尤其值得关注", "从而", "上述", "这表明",
    # 结构词汇（25个）
    "首先", "其次", "最后", "第一", "第二", "第三", "另外", "再者",
    "接下来", "然后", "最终", "进一步", "由此", "因为", "所以",
    "由此可见", "总的来说", "总结一下", "简而言之", "结果是",
    "如前所述", "总之", "说到最后", "当然",
]

REPLACEMENTS = {
    "然而": "但/可/不过，或句号断开下一句直接转折",
    "此外": "删掉，直接接下一句",
    "另外": "删掉，直接接下一句",
    "总之": "用一个有力量的金句代替总结",
    "因此": "所以/这才有了/于是",
    "综上所述": "用一个有力量的金句代替总结",
    "值得注意的是": "删掉，直接说值得注意的事",
    "首先": "用关键词小标题或场景推进代替",
    "其次": "用关键词小标题或场景推进代替",
    "最后": "用关键词小标题或场景推进代替",
    "第一": "用关键词小标题代替编号",
    "第二": "用关键词小标题代替编号",
    "第三": "用关键词小标题代替编号",
    "总的来说": "删掉，用金句收束",
    "总结一下": "删掉，用金句收束",
    "简而言之": "删掉，用金句收束",
    "显而易见": "删掉，直接陈述事实",
    "毫无疑问": "删掉，直接陈述事实",
    "不可否认": "删掉，直接陈述事实",
    "尽管如此": "话是这么说/道理是这个道理",
    "换句话说": "说白了/意思是",
    "所以": "可保留（口语化），视上下文决定",
    "因为": "可保留（口语化），视上下文决定",
}


def scan_article(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    hits = []

    for line_num, line in enumerate(lines, 1):
        for word in FORBIDDEN_WORDS:
            if word in line:
                # 避免误报：检查是否是独立词汇
                pattern = re.escape(word)
                if re.search(pattern, line):
                    replacement = REPLACEMENTS.get(word, "删掉或重构句子")
                    hits.append({
                        "line": line_num,
                        "word": word,
                        "context": line.strip()[:80],
                        "suggestion": replacement,
                    })

    # 去重（同一行同一个词只报一次）
    seen = set()
    unique_hits = []
    for hit in hits:
        key = (hit["line"], hit["word"])
        if key not in seen:
            seen.add(key)
            unique_hits.append(hit)

    # 输出
    print(f"\n📄 扫描文件: {filepath}")
    print(f"📊 总行数: {len(lines)}")
    print(f"🚨 违禁词命中: {len(unique_hits)} 处\n")

    if not unique_hits:
        print("✅ 恭喜！全文零违禁词命中。")
        return

    print("=" * 60)
    for hit in unique_hits:
        print(f"  行 {hit['line']:>4} | 「{hit['word']}」")
        print(f"         | 上下文: {hit['context']}...")
        print(f"         | 建议: {hit['suggestion']}")
        print("-" * 60)

    # 统计
    word_counts = {}
    for hit in unique_hits:
        w = hit["word"]
        word_counts[w] = word_counts.get(w, 0) + 1

    print("\n📈 违禁词频率统计:")
    for word, count in sorted(word_counts.items(), key=lambda x: -x[1]):
        print(f"  「{word}」: {count} 次")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python forbidden_word_scan.py <article_file.md>")
        sys.exit(1)
    scan_article(sys.argv[1])
