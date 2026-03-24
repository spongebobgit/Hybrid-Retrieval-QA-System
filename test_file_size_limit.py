#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件大小限制测试脚本

测试后端文件大小限制功能：
1. 单个文件超过10MB限制
2. 总文件大小超过50MB限制
3. 正常文件上传（小于限制）

注意：运行前需要启动FastAPI服务（python app.py）
"""

import requests
import os
import tempfile

# FastAPI服务器地址
BASE_URL = "http://localhost:8001"

def test_health():
    """测试健康检查端点"""
    response = requests.get(f"{BASE_URL}/health")
    print(f"健康检查: {response.status_code} - {response.json()}")
    return response.status_code == 200

def create_test_file(filename, size_bytes):
    """创建指定大小的测试文件"""
    with open(filename, 'wb') as f:
        # 写入随机数据，但为了简单，写入重复的字节
        chunk_size = 1024 * 1024  # 1MB
        chunk = b'X' * 1024  # 1KB的块
        bytes_written = 0
        while bytes_written < size_bytes:
            write_size = min(len(chunk), size_bytes - bytes_written)
            f.write(chunk[:write_size])
            bytes_written += write_size
    return filename

def test_single_file_limit():
    """测试单个文件大小限制（10MB）"""
    print(f"\n=== 测试单个文件大小限制 ===")

    # 创建刚好超过10MB的文件（10MB + 1KB）
    oversized_file = "test_oversized.bin"
    create_test_file(oversized_file, 10 * 1024 * 1024 + 1024)  # 10MB + 1KB

    try:
        files = {'files': open(oversized_file, 'rb')}
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        print(f"上传超过10MB文件: {response.status_code} - {response.json()}")

        # 应该返回400错误
        if response.status_code == 400 and "超过" in response.json().get("error", ""):
            print("✓ 单个文件大小限制测试通过")
            return True
        else:
            print("✗ 单个文件大小限制测试失败")
            return False
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        return False
    finally:
        files['files'].close()
        if os.path.exists(oversized_file):
            os.remove(oversized_file)

def test_total_size_limit():
    """测试总文件大小限制（50MB）"""
    print(f"\n=== 测试总文件大小限制 ===")

    # 创建5个文件，每个11MB，总大小55MB（超过50MB限制）
    file_list = []
    try:
        for i in range(5):
            filename = f"test_large_{i}.bin"
            create_test_file(filename, 11 * 1024 * 1024)  # 11MB每个
            file_list.append(filename)

        # 准备多文件上传
        files = [('files', open(fname, 'rb')) for fname in file_list]
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        print(f"上传多个大文件（总大小55MB）: {response.status_code} - {response.json()}")

        # 应该返回400错误
        if response.status_code == 400 and "总文件大小" in response.json().get("error", ""):
            print("✓ 总文件大小限制测试通过")
            result = True
        else:
            print("✗ 总文件大小限制测试失败")
            result = False
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        result = False
    finally:
        # 清理文件
        for f in files:
            f[1].close()
        for fname in file_list:
            if os.path.exists(fname):
                os.remove(fname)
    return result

def test_valid_file_upload():
    """测试正常文件上传（小于限制）"""
    print(f"\n=== 测试正常文件上传 ===")

    # 创建小于10MB的文件
    valid_file = "test_valid.bin"
    create_test_file(valid_file, 5 * 1024 * 1024)  # 5MB

    try:
        files = {'files': open(valid_file, 'rb')}
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        print(f"上传5MB文件: {response.status_code} - {response.json()}")

        # 应该返回200成功
        if response.status_code == 200:
            print("✓ 正常文件上传测试通过")
            return True
        else:
            print("✗ 正常文件上传测试失败")
            return False
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        return False
    finally:
        files['files'].close()
        if os.path.exists(valid_file):
            os.remove(valid_file)

def test_multiple_valid_files():
    """测试多个正常文件上传（总大小小于50MB）"""
    print(f"\n=== 测试多个正常文件上传 ===")

    # 创建3个文件，每个8MB，总大小24MB
    file_list = []
    try:
        for i in range(3):
            filename = f"test_valid_multi_{i}.bin"
            create_test_file(filename, 8 * 1024 * 1024)  # 8MB每个
            file_list.append(filename)

        # 准备多文件上传
        files = [('files', open(fname, 'rb')) for fname in file_list]
        response = requests.post(f"{BASE_URL}/api/upload", files=files)
        print(f"上传多个文件（总大小24MB）: {response.status_code} - {response.json()}")

        # 应该返回200成功
        if response.status_code == 200:
            print("✓ 多个正常文件上传测试通过")
            result = True
        else:
            print("✗ 多个正常文件上传测试失败")
            result = False
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        result = False
    finally:
        # 清理文件
        for f in files:
            f[1].close()
        for fname in file_list:
            if os.path.exists(fname):
                os.remove(fname)
    return result

def main():
    """主测试函数"""
    print("=== 文件大小限制功能测试 ===\n")

    # 检查服务器是否运行
    if not test_health():
        print("服务器未运行，请先启动: python app.py")
        return

    # 运行测试
    tests = [
        ("单个文件大小限制", test_single_file_limit),
        ("总文件大小限制", test_total_size_limit),
        ("正常文件上传", test_valid_file_upload),
        ("多个正常文件上传", test_multiple_valid_files),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"{test_name} 测试异常: {e}")

    print(f"\n=== 测试结果 ===")
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("✓ 所有测试通过！")
    else:
        print("✗ 部分测试失败")

if __name__ == "__main__":
    main()