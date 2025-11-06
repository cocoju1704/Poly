"""템플릿 로더 유틸리티"""
import os
import streamlit as st
from pathlib import Path


def get_template_path(template_name: str) -> Path:
    """템플릿 파일 경로 반환"""
    base_dir = Path(__file__).parent.parent.parent
    template_path = base_dir / "templates" / template_name
    return template_path


def load_template(template_name: str, **kwargs) -> str:
    """템플릿 파일을 로드하고 변수 치환"""
    try:
        template_path = get_template_path(template_name)
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 변수 치환
        if kwargs:
            content = content.format(**kwargs)
        
        return content
    except FileNotFoundError:
        st.warning(f"템플릿 파일을 찾을 수 없습니다: {template_name}")
        return ""


def render_template(template_name: str, **kwargs):
    """템플릿을 렌더링하여 Streamlit에 표시"""
    content = load_template(template_name, **kwargs)
    if content:
        st.markdown(content, unsafe_allow_html=True)


def load_css(css_name: str):
    """CSS 파일을 로드하여 Streamlit에 주입"""
    try:
        base_dir = Path(__file__).parent.parent.parent
        css_path = base_dir / "styles" / css_name
        
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
        
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"CSS 파일을 찾을 수 없습니다: {css_name}")



