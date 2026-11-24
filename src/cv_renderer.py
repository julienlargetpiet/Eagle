"""Render a tailored CV through Jinja2 and pdflatex."""

import re
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def escape_latex(text):
    if not isinstance(text, str):
        return text

    replacements = {
        '\\': r'\textbackslash{}',
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    return re.sub(
        r'[\\&%$#_{}~^]',
        lambda match: replacements[match.group()],
        text,
    )


def create_cv_pdf(cv: dict, folder: Path, template_path: Path) -> Path:
    """The caller owns folder creation; this function only renders files."""
    if not folder.is_dir():
        raise FileNotFoundError(f'Draft folder does not exist: {folder}')

    env = Environment(
        loader=FileSystemLoader(template_path.parent),
        variable_start_string='(((',
        variable_end_string=')))',
        block_start_string='((*',
        block_end_string='*))',
        autoescape=False,
        finalize=escape_latex,
        undefined=StrictUndefined,
    )
    template = env.get_template(template_path.name)
    tex_path = folder / 'cv.tex'
    tex_path.write_text(template.render(**cv), encoding='utf-8')

    process = subprocess.run(
        ['pdflatex', '-interaction=nonstopmode', '-halt-on-error',
         '-no-shell-escape', 'cv.tex'],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f'pdflatex failed:\n{process.stdout[-4000:]}\n'
            f'{process.stderr[-1000:]}'
        )

    pdf_path = folder / 'cv.pdf'
    if not pdf_path.is_file():
        raise RuntimeError('pdflatex did not generate cv.pdf')
    return pdf_path



