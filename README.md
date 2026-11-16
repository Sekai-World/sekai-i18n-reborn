# Sekai Viewer translations

Flat JSON dictionaries for Sekai Viewer Reborn. Each top-level directory is a
repository locale; each JSON file is a namespace. English source keys are owned
by [`sekai-viewer-reborn/packages/i18n-source`](https://github.com/Sekai-World/sekai-viewer-reborn/tree/main/packages/i18n-source).

| Site | Dictionary path | English source |
| --- | --- | --- |
| content-site | `<locale>/<namespace>.json` | `packages/i18n-source/content-site` |
| tools-site | `<locale>/tools-site/<namespace>.json` | `packages/i18n-source/tools-site` |
| media-lab-site | `<locale>/media-lab-site/<namespace>.json` | `packages/i18n-source/media-lab-site` |

The sites reuse namespace names such as `common`, so every site other than
content-site keeps its files in its own subdirectory. content-site stays at the
locale root because deployed viewers already load it from there.

## Translation policy

- Keep existing translations when adding missing keys or namespaces.
- New translations in the locale-coverage expansion are independently AI-assisted
  translations of the reborn English source, **not imports from `sekai-i18n`**.
  Existing reborn translations retain their original history and provenance.
- Preserve keys, placeholders, URLs, and markup. Translate interface text; keep
  product names and other proper nouns where appropriate.
- Structural validation establishes dictionary coverage and placeholder safety,
  not native-speaker review. Language-specific terminology and naturalness still
  benefit from community review.
- Do not fill untranslated entries with English merely to satisfy coverage checks.

## Validation

Requires Python 3, with no third-party dependencies:

```sh
python3 scripts/validate_dictionaries.py
python3 scripts/validate_dictionaries.py \
  --source-dir /path/to/sekai-viewer-reborn/packages/i18n-source/content-site \
  --site-source-dir tools-site=/path/to/sekai-viewer-reborn/packages/i18n-source/tools-site \
  --site-source-dir media-lab-site=/path/to/sekai-viewer-reborn/packages/i18n-source/media-lab-site
python3 -B -m unittest discover -s tests -v
```

The expected locale set has 29 entries. The source snapshot used for this
expansion is viewer commit `080d907d`: 15 namespaces and 978 keys per locale.
The validator reads the source files rather than hard-coding that key count.
Without `--source-dir` it compares every locale with `en/`, site subdirectories
included. A site subdirectory must exist in every locale once it exists in one.

Deploy coordinated dictionary changes before enabling new locales in the viewer.
The viewer maps UI codes `ja-JP` and `ko-KR` to repository directories `ja` and `ko`.
Regional directory names use hyphens, including `ca-ES`, `es-419`, `es-MX`,
`he-IL`, `sk-SK`, and `vi-VN`.

## 中文说明

本仓库保存新版 Sekai Viewer 的分命名空间扁平 JSON 字典；英文词条由上述
viewer 仓库维护。content-site 的字典位于语言目录根部，tools-site 和
media-lab-site 的字典位于各自的子目录（如 `ja/tools-site/common.json`）。补全时保留新版已有译文，新增译文根据新版英文独立进行
AI 辅助翻译，不移植旧版 `sekai-i18n` 译文。

校验可确认词条覆盖和占位符兼容性，不代表经过全部语种的母语审校。请继续
通过社区审校改进术语和表达；不要使用英文填充来冒充已翻译。新增语言应先
部署字典，再启用前端对应语言配置。
