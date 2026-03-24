#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件上传功能测试脚本

注意：运行前需要启动FastAPI服务（python app.py）
"""

import requests
import os
import json

# FastAPI服务器地址
BASE_URL = "http://localhost:8001"

def test_health():
    """测试健康检查端点"""
    response = requests.get(f"{BASE_URL}/health")
    print(f"健康检查: {response.status_code} - {response.json()}")
    return response.status_code == 200

def test_get_sources():
    """测试获取学科类别"""
    response = requests.get(f"{BASE_URL}/api/sources")
    print(f"学科类别: {response.status_code} - {response.json()}")
    return response.status_code == 200

def test_get_stats():
    """测试获取知识库统计"""
    response = requests.get(f"{BASE_URL}/api/knowledgebase/stats")
    print(f"知识库统计: {response.status_code} - {response.json()}")
    return response.status_code == 200

def test_upload_file(file_path, source=None):
    """测试上传文件"""
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
        return False

    files = {'files': open(file_path, 'rb')}
    data = {}
    if source:
        data['source'] = source

    try:
        response = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
        print(f"上传文件 {file_path}: {response.status_code} - {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"上传失败: {e}")
        return False
    finally:
        files['files'].close()

def create_test_file(filename, content="这是一个测试文档内容。\n用于测试文件上传功能。"):
    """创建测试文件"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return filename

def main():
    """主测试函数"""
    print("=== 文件上传功能测试 ===\n")

    # 检查服务器是否运行
    if not test_health():
        print("服务器未运行，请先启动: python app.py")
        return

    # 获取学科类别
    if not test_get_sources():
        print("获取学科类别失败")
        return

    # 获取当前统计
    test_get_stats()

    # 创建测试文件
    test_filename = "test_document.txt"
    create_test_file(test_filename)

    print(f"\n=== 测试上传文件 ===")
    # 测试上传文件（不带学科类别）
    success1 = test_upload_file(test_filename)

    # 测试上传文件（带学科类别）
    success2 = test_upload_file(test_filename, source="test")

    # 清理测试文件
    if os.path.exists(test_filename):
        os.remove(test_filename)

    # 获取更新后的统计
    if success1 or success2:
        print(f"\n=== 上传后统计 ===")
        test_get_stats()

    # 测试删除功能（可选）
    # print(f"\n=== 测试删除功能 ===")
    # response = requests.delete(f"{BASE_URL}/api/knowledgebase/test")
    # print(f"删除test学科文档: {response.status_code} - {response.json()}")

    print(f"\n=== 测试完成 ===")

if __name__ == "__main__":
    main()