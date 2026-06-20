#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书视频语音转写处理器
使用 Groq API + Whisper 模型从视频音频中提取文字
"""

import os
import subprocess
import re
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import tempfile
import shutil

try:
    from groq import Groq
except ImportError:
    print("❌ 未安装 groq 库，请运行: pip install groq")
    exit(1)


# ============== 配置 ==============

DEFAULT_API_KEY = os.getenv('GROQ_API_KEY', '')  # 从环境变量获取API密钥
DEFAULT_MODEL = "whisper-large-v3-turbo"  # 可选: whisper-large-v3
DEFAULT_CHUNK_DURATION = 300  # 5分钟
DEFAULT_MAX_CONCURRENT = 3
DEFAULT_MAX_FILE_SIZE_MB = 25
DEFAULT_LANGUAGE = None  # None=自动检测, zh=中文, en=英文


# ============== 工具函数 ==============

def format_timestamp(seconds):
    """将秒数转换为 HH:MM:SS 格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_file_size(size_bytes):
    """格式化文件大小"""
    size_mb = size_bytes / (1024 * 1024)
    if size_mb < 1024:
        return f"{size_mb:.1f}MB"
    else:
        size_gb = size_mb / 1024
        return f"{size_gb:.2f}GB"


def check_ffmpeg():
    """检查系统是否安装了ffmpeg"""
    try:
        subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            check=True,
            timeout=5
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_video_duration(video_path):
    """
    获取视频时长（秒）

    Args:
        video_path: 视频文件路径

    Returns:
        float: 时长（秒）
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )

        duration = float(result.stdout.strip())
        return duration

    except subprocess.CalledProcessError:
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"  ⚠️  获取视频时长失败: {e}")
        return None


def should_split_video(video_path, max_size_mb=DEFAULT_MAX_FILE_SIZE_MB):
    """
    判断是否需要切分视频

    Args:
        video_path: 视频文件路径
        max_size_mb: 最大文件大小（MB）

    Returns:
        bool: 是否需要切分
    """
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    return file_size_mb > max_size_mb


# ============== 视频切分功能 ==============

def split_video_ffmpeg(video_path, output_dir, chunk_duration=300):
    """
    使用ffmpeg切分视频，不重新编码（快速）

    Args:
        video_path: 原视频路径
        output_dir: 输出目录
        chunk_duration: 每段时长（秒）

    Returns:
        list: 切分后的文件路径列表，失败返回None
    """
    try:
        # 获取视频时长
        duration = get_video_duration(video_path)
        if duration is None:
            print(f"  ⚠️  无法获取视频时长，尝试直接上传")
            return None

        print(f"  📹 视频时长: {format_timestamp(duration)}, 文件大小: {format_file_size(os.path.getsize(video_path))}")

        # 如果视频很短，不需要切分
        if duration <= chunk_duration:
            print(f"  ✅ 视频较短（{format_timestamp(duration)}），无需切分")
            return [video_path]

        chunks = []
        start_time = 0
        chunk_index = 0

        while start_time < duration:
            end_time = min(start_time + chunk_duration, duration)

            output_file = output_dir / f"chunk_{chunk_index:03d}.mp4"

            print(f"  📝 切分片段 {chunk_index + 1}: {format_timestamp(start_time)} - {format_timestamp(end_time)}")

            # 使用ffmpeg切分（-c copy 不重新编码）
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-ss', str(start_time),
                '-t', str(end_time - start_time),
                '-c', 'copy',  # 不重新编码，速度快
                '-y',  # 覆盖输出文件
                '-loglevel', 'error',  # 只显示错误
                str(output_file)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                timeout=300  # 5分钟超时
            )

            if result.returncode != 0:
                print(f"  ❌ 切分失败: {result.stderr.decode()}")
                # 清理已创建的片段
                for chunk in chunks:
                    if chunk.exists() and chunk != video_path:
                        chunk.unlink()
                return None

            chunks.append(output_file)
            start_time = end_time
            chunk_index += 1

        print(f"  ✅ 成功切分为 {len(chunks)} 个片段")
        return chunks

    except subprocess.TimeoutExpired:
        print(f"  ❌ 切分超时")
        return None
    except Exception as e:
        print(f"  ❌ 切分失败: {e}")
        return None


# ============== 异步转写功能 ==============

async def transcribe_video_chunk(client, chunk_path, config, chunk_index=0, total_chunks=1):
    """
    异步转写单个视频片段

    Args:
        client: Groq API客户端
        chunk_path: 视频片段路径
        config: 配置字典
        chunk_index: 片段索引
        total_chunks: 总片段数

    Returns:
        dict: {index, text, success, error}
    """
    max_retries = config.get('retry_attempts', 3)

    for attempt in range(max_retries):
        try:
            # 在线程池中执行同步的API调用
            loop = asyncio.get_event_loop()

            def do_transcribe():
                with open(chunk_path, 'rb') as f:
                    file_content = f.read()

                return client.audio.transcriptions.create(
                    file=(os.path.basename(chunk_path), file_content),
                    model=config['model'],
                    language=config.get('language'),
                    response_format='json',
                    temperature=config.get('temperature', 0.0)
                )

            result = await loop.run_in_executor(None, do_transcribe)

            return {
                'index': chunk_index,
                'text': result.text,
                'success': True,
                'error': None
            }

        except Exception as e:
            error_msg = str(e)

            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * config.get('delay_between_chunks', 1)
                print(f"  ⚠️  片段 {chunk_index + 1}/{total_chunks} 转写失败（尝试 {attempt + 1}/{max_retries}），{wait_time}秒后重试: {error_msg}")
                await asyncio.sleep(wait_time)
            else:
                print(f"  ❌ 片段 {chunk_index + 1}/{total_chunks} 转写失败: {error_msg}")
                return {
                    'index': chunk_index,
                    'text': None,
                    'success': False,
                    'error': error_msg
                }

    return {
        'index': chunk_index,
        'text': None,
        'success': False,
        'error': 'Max retries exceeded'
    }


async def process_single_video(video_path, output_file, config, temp_dir=None):
    """
    处理单个视频文件

    Args:
        video_path: 视频文件路径
        output_file: 输出文本文件路径
        config: 配置字典
        temp_dir: 临时目录（用于切分片段）

    Returns:
        dict: 处理统计信息
    """
    print(f"\n{'='*60}")
    print(f"🎬 处理视频: {video_path.name}")
    print(f"{'='*60}")

    # 检查输出文件是否已存在
    if not config.get('force', False) and output_file.exists():
        return {
            'status': 'skipped',
            'reason': '已存在转写结果文件',
            'video': video_path.name
        }

    # 如果是预览模式
    if not config.get('enabled', True):
        return {
            'status': 'preview',
            'video': video_path.name
        }

    client = Groq(api_key=config['api_key'])

    # 步骤1: 判断是否需要切分
    chunks = [video_path]  # 默认不切分

    if config.get('split_videos', False) and check_ffmpeg():
        if should_split_video(video_path, config.get('max_file_size_mb', DEFAULT_MAX_FILE_SIZE_MB)):
            print(f"  📊 文件大小超过 {config.get('max_file_size_mb', DEFAULT_MAX_FILE_SIZE_MB)}MB，进行切分...")

            # 创建临时目录
            if temp_dir is None:
                temp_dir = Path(tempfile.mkdtemp(prefix='video_chunks_'))

            chunks = split_video_ffmpeg(
                video_path,
                temp_dir,
                config.get('chunk_duration', DEFAULT_CHUNK_DURATION)
            )

            if chunks is None:
                print(f"  ⚠️  切分失败，尝试直接上传")
                chunks = [video_path]
            elif len(chunks) == 1 and chunks[0] == video_path:
                print(f"  ℹ️  视频无需切分")
        else:
            print(f"  ✅ 文件大小合适，直接上传")
    else:
        if not config.get('split_videos', False):
            print(f"  ℹ️  视频切分已禁用，直接上传")
        else:
            print(f"  ⚠️  未检测到ffmpeg，直接上传（建议安装: brew install ffmpeg）")

    # 步骤2: 异步转写各个片段
    total_chunks = len(chunks)
    print(f"\n  🔄 开始转写 {total_chunks} 个片段...")

    results = []

    for i, chunk_path in enumerate(chunks):
        print(f"  📖 正在转写片段 {i + 1}/{total_chunks}...")
        result = await transcribe_video_chunk(client, chunk_path, config, i, total_chunks)
        results.append(result)

        # 片段间延迟
        delay = config.get('delay_between_chunks', 1)
        if delay > 0 and i < total_chunks - 1:
            await asyncio.sleep(delay)

    # 步骤3: 清理临时文件
    if temp_dir and temp_dir.exists() and not config.get('keep_chunks', False):
        try:
            shutil.rmtree(temp_dir)
            print(f"  🧹 已清理临时文件")
        except Exception as e:
            print(f"  ⚠️  清理临时文件失败: {e}")

    # 步骤4: 合并结果并保存
    success_count = sum(1 for r in results if r['success'])
    failed_count = total_chunks - success_count

    if success_count == 0:
        return {
            'status': 'error',
            'reason': '所有片段转写失败',
            'video': video_path.name
        }

    # 合并文本
    full_text = []
    for i, result in enumerate(sorted(results, key=lambda x: x['index'])):
        if result['success'] and result['text']:
            full_text.append(result['text'])

    combined_text = '\n\n'.join(full_text)

    # 获取视频总时长
    duration = get_video_duration(video_path)
    duration_str = format_timestamp(duration) if duration else "未知"

    # 保存结果
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("视频语音转写结果\n")
            f.write("=" * 60 + "\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"API提供商: Groq\n")
            f.write(f"模型: {config['model']}\n")
            f.write(f"视频文件: {video_path.name}\n")
            f.write(f"视频时长: {duration_str}\n")
            if config.get('language'):
                lang_name = "中文" if config['language'] == 'zh' else "英文"
                f.write(f"识别语言: {lang_name}\n")
            else:
                f.write(f"识别语言: 自动检测\n")
            f.write("=" * 60 + "\n\n")

            for i, result in enumerate(sorted(results, key=lambda x: x['index'])):
                if result['success'] and result['text']:
                    chunk_duration = config.get('chunk_duration', DEFAULT_CHUNK_DURATION)
                    start = i * chunk_duration
                    end = min(start + chunk_duration, int(duration)) if duration else start + chunk_duration

                    f.write(f"📝 片段 {i + 1} ({format_timestamp(start)} - {format_timestamp(end)})\n")
                    f.write("-" * 40 + "\n")
                    f.write(f"{result['text']}\n\n")

            f.write("-" * 60 + "\n")
            f.write(f"统计: 共处理 {total_chunks} 个片段，成功 {success_count} 个，失败 {failed_count} 个\n")
            f.write(f"总字数: {len(combined_text)} 字\n")

        print(f"  ✅ 结果已保存: {output_file.name}")

    except Exception as e:
        return {
            'status': 'error',
            'reason': f'保存结果文件失败: {str(e)}',
            'video': video_path.name
        }

    return {
        'status': 'success',
        'chunks_processed': total_chunks,
        'success_count': success_count,
        'failed_count': failed_count,
        'total_words': len(combined_text),
        'video': video_path.name
    }


# ============== 批量处理 ==============

def find_video_files(root_dir):
    """
    查找所有视频文件

    Args:
        root_dir: 根目录路径

    Returns:
        list: 视频文件路径列表 (仅包含 视频_*.mp4)
    """
    root_path = Path(root_dir)
    video_files = []

    # 查找所有子目录
    for item in root_path.iterdir():
        if item.is_dir():
            # 检查是否匹配笔记文件夹命名模式
            match = re.match(r'^\d{3}_.+_[a-f0-9]{8}$', item.name)
            if match:
                # 查找视频文件
                videos = list(item.glob('视频_*.mp4'))
                video_files.extend(videos)

    return sorted(video_files)


async def process_all_videos(root_dir, config, parallel=True):
    """
    批量处理所有视频

    Args:
        root_dir: 根目录路径
        config: 配置字典
        parallel: 是否并行处理

    Returns:
        dict: 统计信息
    """
    root_path = Path(root_dir)
    if not root_path.exists():
        print(f"❌ 目录不存在: {root_dir}")
        return None

    # 查找所有视频文件
    video_files = find_video_files(root_dir)

    if not video_files:
        print(f"❌ 未找到任何视频文件")
        print(f"   搜索路径: {root_path.absolute()}")
        return None

    print(f"🔍 找到 {len(video_files)} 个视频文件\n")

    stats = {
        'total': len(video_files),
        'success': 0,
        'skipped': 0,
        'error': 0,
        'preview': 0,
        'total_chunks': 0,
        'success_chunks': 0,
        'failed_chunks': 0,
        'total_words': 0
    }

    if parallel and len(video_files) > 1 and config.get('enabled', True):
        # 并行处理
        workers = config.get('max_concurrent', DEFAULT_MAX_CONCURRENT)
        print(f"🚀 使用 {workers} 个线程并行处理...\n")

        # 创建临时目录
        temp_dir = Path(tempfile.mkdtemp(prefix='video_transcriber_'))

        try:
            # 使用信号量控制并发数
            semaphore = asyncio.Semaphore(workers)

            async def process_with_semaphore(video_path):
                async with semaphore:
                    output_file = video_path.parent / "视频转写结果.txt"
                    return await process_single_video(video_path, output_file, config, temp_dir)

            tasks = [process_with_semaphore(video) for video in video_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    print(f"❌ 处理异常: {result}")
                    stats['error'] += 1
                elif result:
                    stats = update_stats(stats, result)

        finally:
            # 清理临时目录
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass

    else:
        # 串行处理
        print(f"📝 串行处理...\n")

        for video_path in video_files:
            output_file = video_path.parent / "视频转写结果.txt"
            result = await process_single_video(video_path, output_file, config)
            if result:
                stats = update_stats(stats, result)

    return stats


def update_stats(stats, result):
    """更新统计信息"""
    status = result.get('status', '')

    if status == 'success':
        stats['success'] += 1
        stats['total_chunks'] += result.get('chunks_processed', 0)
        stats['success_chunks'] += result.get('success_count', 0)
        stats['failed_chunks'] += result.get('failed_count', 0)
        stats['total_words'] += result.get('total_words', 0)
    elif status == 'skipped':
        stats['skipped'] += 1
    elif status == 'preview':
        stats['preview'] += 1
    elif status == 'error':
        stats['error'] += 1

    return stats


def print_summary(stats):
    """打印统计摘要"""
    print("\n" + "=" * 60)
    print("📊 处理完成统计")
    print("=" * 60)
    print(f"总视频数: {stats['total']}")
    print(f"✅ 成功处理: {stats['success']}")
    print(f"⏭️  已存在跳过: {stats['skipped']}")

    if stats.get('preview', 0) > 0:
        print(f"👀️  预览模式: {stats['preview']}")

    if stats.get('error', 0) > 0:
        print(f"❌ 处理失败: {stats['error']}")

    if stats['total_chunks'] > 0:
        print(f"\n🎬 视频处理统计:")
        print(f"   总片段数: {stats['total_chunks']}")
        print(f"   识别成功: {stats['success_chunks']}")
        print(f"   识别失败: {stats['failed_chunks']}")
        if stats['total_words'] > 0:
            print(f"   总字数: {stats['total_words']:,} 字")

    print("=" * 60)


# ============== 主程序 ==============

def main():
    parser = argparse.ArgumentParser(
        description='小红书视频语音转写处理器 - 使用Groq API + Whisper从视频音频中提取文字',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本用法
  python video_transcriber.py -d xiaohongshu_downloads/20260123_090604_我爱上班搞笑朗诵台词

  # 预览模式（不执行转写）
  python video_transcriber.py -d xiaohongshu_downloads/20260123_* --no-transcribe

  # 使用更高准确度的模型
  python video_transcriber.py -d xiaohongshu_downloads/20260123_* --model whisper-large-v3

  # 强制重新处理
  python video_transcriber.py -d xiaohongshu_downloads/20260123_* --force
        """
    )

    parser.add_argument('-d', '--directory', required=True,
                       help='包含下载笔记的根目录路径（必需）')
    parser.add_argument('--no-transcribe', action='store_true',
                       help='预览模式：扫描但不执行转写')
    parser.add_argument('--api-key', default=None,
                       help=f'Groq API密钥（默认: 使用环境变量GROQ_API_KEY或内置密钥）')
    parser.add_argument('--model', default=DEFAULT_MODEL,
                       choices=['whisper-large-v3-turbo', 'whisper-large-v3'],
                       help='Whisper模型（默认: whisper-large-v3-turbo）')
    parser.add_argument('--language', default=DEFAULT_LANGUAGE,
                       choices=['zh', 'en', 'auto'],
                       help='识别语言: zh=中文, en=英文, auto=自动检测（默认: auto）')
    parser.add_argument('--chunk-duration', type=int, default=DEFAULT_CHUNK_DURATION,
                       help='视频切分时长（秒，默认: 300）')
    parser.add_argument('--max-concurrent', type=int, default=DEFAULT_MAX_CONCURRENT,
                       help='并行处理的视频数（默认: 3）')
    parser.add_argument('--max-file-size', type=int, default=DEFAULT_MAX_FILE_SIZE_MB,
                       help='超过此大小(MB)的视频将被切分（默认: 25）')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='片段间延迟秒数，避免限流（默认: 1.0）')
    parser.add_argument('--retry', type=int, default=3,
                       help='失败重试次数（默认: 3）')
    parser.add_argument('--force', action='store_true',
                       help='强制重新处理已存在的结果文件')
    parser.add_argument('--keep-chunks', action='store_true',
                       help='保留视频切分片段（用于调试）')
    parser.add_argument('--no-split', action='store_true',
                       help='禁用视频切分，直接上传（大文件可能失败）')
    parser.add_argument('--no-parallel', action='store_true',
                       help='禁用并行处理，使用串行模式')

    args = parser.parse_args()

    # 获取API密钥
    api_key = args.api_key or os.getenv('GROQ_API_KEY', DEFAULT_API_KEY)

    # 构建配置
    config = {
        'enabled': not args.no_transcribe,
        'api_key': api_key,
        'model': args.model,
        'language': None if args.language == 'auto' else args.language,
        'chunk_duration': args.chunk_duration,
        'max_concurrent': args.max_concurrent,
        'max_file_size_mb': args.max_file_size,
        'temperature': 0.0,
        'delay_between_chunks': args.delay,
        'retry_attempts': args.retry,
        'force': args.force,
        'keep_chunks': args.keep_chunks,
        'split_videos': not args.no_split
    }

    # 打印配置信息
    print("🎬 小红书视频语音转写处理器")
    print("=" * 60)
    print(f"目标目录: {args.directory}")
    print(f"转写模式: {'启用' if config['enabled'] else '预览（不执行转写）'}")
    if config['enabled']:
        print(f"模型: {config['model']}")
        print(f"识别语言: {'中文' if config['language'] == 'zh' else '英文' if config['language'] == 'en' else '自动检测'}")
        print(f"视频切分: {'启用' if config['split_videos'] else '禁用'}")
        if config['split_videos']:
            print(f"最大文件大小: {config['max_file_size_mb']}MB")
            print(f"切分时长: {config['chunk_duration']}秒")
        print(f"处理模式: {'并行' if not args.no_parallel else '串行'}")
        if not args.no_parallel:
            print(f"最大并发数: {config['max_concurrent']}")
    print("=" * 60 + "\n")

    # 检查ffmpeg
    if config['split_videos']:
        if check_ffmpeg():
            print("✅ 检测到ffmpeg，视频切分功能可用\n")
        else:
            print("⚠️  未检测到ffmpeg，将直接上传视频")
            print("   建议安装ffmpeg以支持大文件处理:")
            print("   macOS: brew install ffmpeg")
            print("   Ubuntu: sudo apt-get install ffmpeg\n")
            config['split_videos'] = False

    # 处理所有视频
    stats = asyncio.run(
        process_all_videos(
            root_dir=args.directory,
            config=config,
            parallel=not args.no_parallel
        )
    )

    # 打印统计摘要
    if stats:
        print_summary(stats)


if __name__ == "__main__":
    main()
