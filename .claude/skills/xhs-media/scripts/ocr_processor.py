#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书图片OCR识别处理器
使用 OCR.space API 从已下载的笔记图片中提取文字
"""

import os
import requests
import re
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


def ocr_space_file(filename, overlay=False, api_key='helloworld', language='chs', engine='1', timeout=30):
    """
    OCR.space API 请求函数

    Args:
        filename: 本地图片文件的路径
        overlay: 是否需要返回文字坐标 (默认: False)
        api_key: OCR.space API Key
        language: 识别语言 (chs=简体中文, eng=英语)
        engine: OCR引擎 ('1', '2', 或 '3')
        timeout: 请求超时时间（秒）

    Returns:
        str: 识别出的文本，如果失败则返回错误信息
    """
    payload = {
        'isOverlayRequired': overlay,
        'apikey': api_key,
        'language': language,
        'detectOrientation': True,
        'scale': True,
        'OCREngine': engine,
    }

    try:
        with open(filename, 'rb') as f:
            r = requests.post('https://api.ocr.space/parse/image',
                              files={'file': f},
                              data=payload,
                              timeout=timeout)

        r.raise_for_status()
        result = r.json()

        # 检查是否处理出错
        if result.get('IsErroredOnProcessing', False):
            error_msg = result.get('ErrorMessage', '未知错误')
            return f"OCR_ERROR: {error_msg}"

        # 提取识别结果
        if 'ParsedResults' in result and len(result['ParsedResults']) > 0:
            parsed_text = result['ParsedResults'][0].get('ParsedText', '')
            if parsed_text and parsed_text.strip():
                # 清理多余的空白字符
                parsed_text = ' '.join(parsed_text.split())
                return parsed_text
            else:
                return "[未识别到文字]"
        else:
            return "[未识别到文字]"

    except FileNotFoundError:
        return f"OCR_ERROR: 找不到文件 {filename}"
    except requests.exceptions.Timeout:
        return f"OCR_ERROR: 请求超时 (>{timeout}秒)"
    except requests.exceptions.RequestException as e:
        return f"OCR_ERROR: 网络请求失败 - {str(e)}"
    except Exception as e:
        return f"OCR_ERROR: {str(e)}"


def filter_content_images(image_paths):
    """
    过滤出内容图片，排除头像图片

    Args:
        image_paths: 图片路径列表

    Returns:
        list: 仅包含内容图片的路径列表 (以"图片_"开头，不以"头像_"开头)
    """
    content_images = []
    for img_path in image_paths:
        filename = img_path.name
        # 排除头像图片
        if filename.startswith('头像_'):
            continue
        # 只处理内容图片
        if filename.startswith('图片_'):
            content_images.append(img_path)

    return content_images


def process_note_folder(note_folder, ocr_config, force=False):
    """
    处理单个笔记文件夹，提取图片中的文字

    Args:
        note_folder: Path对象，笔记文件夹路径
        ocr_config: dict，OCR配置参数
        force: bool，是否强制重新处理已存在的结果文件

    Returns:
        dict: 处理统计信息
    """
    # 检查输出文件是否已存在
    output_file = note_folder / "OCR识别结果.txt"
    if not force and output_file.exists():
        return {
            'status': 'skipped',
            'reason': '已存在OCR结果文件',
            'folder': note_folder.name
        }

    # 查找所有图片文件
    all_images = list(note_folder.glob('*.jpg')) + list(note_folder.glob('*.jpeg')) + \
                 list(note_folder.glob('*.png')) + list(note_folder.glob('*.webp'))

    # 过滤出内容图片（排除头像）
    content_images = filter_content_images(all_images)

    if not content_images:
        return {
            'status': 'no_images',
            'reason': '没有找到内容图片',
            'folder': note_folder.name
        }

    # 如果只是预览模式，不进行实际OCR
    if not ocr_config.get('enabled', True):
        return {
            'status': 'preview',
            'images_count': len(content_images),
            'folder': note_folder.name
        }

    # 处理每张图片
    results = {}
    success_count = 0
    failed_count = 0

    for img_path in sorted(content_images):
        print(f"  📖 正在识别: {note_folder.name}/{img_path.name}")

        # 执行OCR
        extracted_text = ocr_space_file(
            filename=str(img_path),
            api_key=ocr_config['api_key'],
            language=ocr_config['language'],
            engine=ocr_config['engine'],
            timeout=ocr_config.get('timeout', 30)
        )

        results[img_path.name] = extracted_text

        # 统计成功率
        if extracted_text.startswith('OCR_ERROR'):
            failed_count += 1
            print(f"     ❌ 识别失败: {extracted_text}")
        else:
            success_count += 1
            print(f"     ✅ 识别成功 ({len(extracted_text)} 字符)")

        # 延迟以避免API限流
        delay = ocr_config.get('delay', 2)
        if delay > 0 and img_path != sorted(content_images)[-1]:
            time.sleep(delay)

    # 写入结果文件
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("OCR 识别结果\n")
            f.write("=" * 60 + "\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"OCR引擎: OCR.space Engine {ocr_config['engine']}\n")
            f.write(f"识别语言: {'简体中文' if ocr_config['language'] == 'chs' else 'English'}\n")
            f.write("=" * 60 + "\n\n")

            for img_name, text in sorted(results.items()):
                f.write(f"{img_name}:\n")
                f.write("-" * 40 + "\n")
                f.write(f"{text}\n\n")

            f.write("-" * 60 + "\n")
            f.write(f"统计: 共处理 {len(results)} 张图片，成功 {success_count} 张，失败 {failed_count} 张\n")

        print(f"  ✅ 结果已保存: {output_file.name}")

    except Exception as e:
        return {
            'status': 'error',
            'reason': f'保存结果文件失败: {str(e)}',
            'folder': note_folder.name
        }

    return {
        'status': 'success',
        'images_processed': len(results),
        'success_count': success_count,
        'failed_count': failed_count,
        'folder': note_folder.name
    }


def find_note_folders(root_dir):
    """
    在根目录下查找所有笔记文件夹

    Args:
        root_dir: Path对象，根目录路径

    Returns:
        list: 笔记文件夹路径列表
    """
    note_folders = []

    # 查找所有子目录
    for item in root_dir.iterdir():
        if item.is_dir():
            # 检查是否匹配笔记文件夹命名模式: ###_title_########
            # 例如: 000_敬业者联盟~《我爱上班》_65b3504e
            match = re.match(r'^\d{3}_.+_[a-f0-9]{8}$', item.name)
            if match:
                note_folders.append(item)

    return sorted(note_folders)


def process_all_notes(root_dir, ocr_config, parallel=True, force=False):
    """
    批量处理所有笔记文件夹

    Args:
        root_dir: 根目录路径
        ocr_config: OCR配置
        parallel: 是否使用并行处理
        force: 是否强制重新处理

    Returns:
        dict: 整体统计信息
    """
    root_path = Path(root_dir)
    if not root_path.exists():
        print(f"❌ 目录不存在: {root_dir}")
        return None

    # 查找所有笔记文件夹
    note_folders = find_note_folders(root_path)

    if not note_folders:
        print(f"❌ 未找到任何笔记文件夹")
        print(f"   搜索路径: {root_path.absolute()}")
        return None

    print(f"🔍 找到 {len(note_folders)} 个笔记文件夹\n")

    stats = {
        'total': len(note_folders),
        'success': 0,
        'skipped': 0,
        'no_images': 0,
        'preview': 0,
        'error': 0,
        'total_images': 0,
        'success_images': 0,
        'failed_images': 0
    }

    if parallel and len(note_folders) > 1:
        # 并行处理
        workers = ocr_config.get('workers', 3)
        print(f"🚀 使用 {workers} 个线程并行处理...\n")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_folder = {
                executor.submit(process_note_folder, folder, ocr_config, force): folder
                for folder in note_folders
            }

            for future in as_completed(future_to_folder):
                result = future.result()
                if result:
                    stats = update_stats(stats, result)
    else:
        # 串行处理
        print(f"📝 串行处理...\n")

        for folder in note_folders:
            print(f"📁 处理文件夹: {folder.name}")
            result = process_note_folder(folder, ocr_config, force)
            if result:
                stats = update_stats(stats, result)
            print()

    return stats


def update_stats(stats, result):
    """更新统计信息"""
    status = result.get('status', '')

    if status == 'success':
        stats['success'] += 1
        stats['total_images'] += result.get('images_processed', 0)
        stats['success_images'] += result.get('success_count', 0)
        stats['failed_images'] += result.get('failed_count', 0)
    elif status == 'skipped':
        stats['skipped'] += 1
    elif status == 'no_images':
        stats['no_images'] += 1
    elif status == 'preview':
        stats['preview'] += 1
        stats['total_images'] += result.get('images_count', 0)
    elif status == 'error':
        stats['error'] += 1

    return stats


def print_summary(stats):
    """打印统计摘要"""
    print("\n" + "=" * 60)
    print("📊 处理完成统计")
    print("=" * 60)
    print(f"总文件夹数: {stats['total']}")
    print(f"✅ 成功处理: {stats['success']}")
    print(f"⏭️  已存在跳过: {stats['skipped']}")
    print(f"🖼️  无图片跳过: {stats['no_images']}")

    if stats.get('preview', 0) > 0:
        print(f"👀️  预览模式: {stats['preview']}")

    if stats.get('error', 0) > 0:
        print(f"❌ 处理失败: {stats['error']}")

    if stats['total_images'] > 0:
        print(f"\n📸 图片处理统计:")
        print(f"   总图片数: {stats['total_images']}")
        print(f"   识别成功: {stats['success_images']}")
        print(f"   识别失败: {stats['failed_images']}")
        success_rate = (stats['success_images'] / stats['total_images'] * 100) if stats['total_images'] > 0 else 0
        print(f"   成功率: {success_rate:.1f}%")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='小红书图片OCR识别处理器 - 从已下载的笔记图片中提取文字',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本用法
  python ocr_processor.py -d xiaohongshu_downloads/20260123_090604_我爱上班搞笑朗诵台词

  # 使用自定义API密钥
  export OCR_SPACE_API_KEY='your_key_here'
  python ocr_processor.py -d xiaohongshu_downloads/20260123_*

  # 预览模式（不执行OCR）
  python ocr_processor.py -d xiaohongshu_downloads/20260123_* --no-ocr

  # 强制重新处理
  python ocr_processor.py -d xiaohongshu_downloads/20260123_* --force

  # 并行处理（5个线程）
  python ocr_processor.py -d xiaohongshu_downloads/20260123_* --workers 5
        """
    )

    parser.add_argument('-d', '--directory', required=True,
                       help='包含下载笔记的根目录路径（必需）')
    parser.add_argument('--no-ocr', action='store_true',
                       help='预览模式：扫描但不执行OCR识别')
    parser.add_argument('--ocr-api-key', default=None,
                       help='OCR.space API密钥（默认: 使用OCR_SPACE_API_KEY环境变量或"helloworld"）')
    parser.add_argument('--ocr-language', default='chs',
                       choices=['chs', 'eng', 'cht'],
                       help='OCR识别语言: chs=简体中文, eng=英语, cht=繁体中文 (默认: chs)')
    parser.add_argument('--ocr-engine', default='1',
                       choices=['1', '2', '3'],
                       help='OCR引擎: 1=免费引擎, 2=付费引擎, 3=备用引擎 (默认: 1)')
    parser.add_argument('--workers', type=int, default=3,
                       help='并行处理的线程数 (默认: 3)')
    parser.add_argument('--delay', type=float, default=2.0,
                       help='OCR请求之间的延迟秒数，避免限流 (默认: 2.0)')
    parser.add_argument('--timeout', type=int, default=30,
                       help='OCR请求超时时间（秒） (默认: 30)')
    parser.add_argument('--force', action='store_true',
                       help='强制重新处理已存在的结果文件')
    parser.add_argument('--no-parallel', action='store_true',
                       help='禁用并行处理，使用串行模式')

    args = parser.parse_args()

    # 获取API密钥
    api_key = args.ocr_api_key or os.getenv('OCR_SPACE_API_KEY', 'helloworld')

    # 构建OCR配置
    ocr_config = {
        'enabled': not args.no_ocr,
        'api_key': api_key,
        'language': args.ocr_language,
        'engine': args.ocr_engine,
        'workers': args.workers,
        'delay': args.delay,
        'timeout': args.timeout
    }

    # 打印配置信息
    print("🔍 小红书OCR识别处理器")
    print("=" * 60)
    print(f"目标目录: {args.directory}")
    print(f"OCR模式: {'启用' if ocr_config['enabled'] else '预览（不执行识别）'}")
    if ocr_config['enabled']:
        print(f"识别语言: {ocr_config['language']}")
        print(f"OCR引擎: {ocr_config['engine']}")
        print(f"请求延迟: {ocr_config['delay']}秒")
    print(f"处理模式: {'并行' if not args.no_parallel else '串行'}")
    if not args.no_parallel and ocr_config['enabled']:
        print(f"线程数: {ocr_config['workers']}")
    print("=" * 60 + "\n")

    # 处理所有笔记
    stats = process_all_notes(
        root_dir=args.directory,
        ocr_config=ocr_config,
        parallel=not args.no_parallel,
        force=args.force
    )

    # 打印统计摘要
    if stats:
        print_summary(stats)


if __name__ == "__main__":
    main()
