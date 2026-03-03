import os
import asyncio
from typing import List
import uuid

from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

from ..schema import PPTDraft, PPTSection
from ..presenton_core.models.pptx_models import (
    PptxPresentationModel,
    PptxSlideModel,
    PptxTextBoxModel,
    PptxAutoShapeBoxModel,
    PptxPositionModel,
    PptxParagraphModel,
    PptxFontModel,
    PptxSpacingModel,
    PptxTextRunModel,
    PptxFillModel,
    PptxStrokeModel,
    PptxShadowModel,
    PptxPictureBoxModel,
    PptxPictureModel,
    PptxObjectFitEnum,
    PptxObjectFitModel,
)
from ..presenton_core.services.pptx_presentation_creator import PptxPresentationCreator
from .themes import get_theme_config, Theme, create_dynamic_theme, extract_colors_from_image
from .image_generator import generate_image
from .chart_generator import generate_chart
from app.core.logger import get_logger

logger = get_logger(__name__)


def map_draft_to_pptx_model(draft: PPTDraft) -> PptxPresentationModel:
    slides: List[PptxSlideModel] = []
    
    # --- Theme and Color Selection Logic ---
    theme_config = None
    
    # 1. Check for manual color palette
    if draft.color_palette and not draft.use_default_colors:
        theme_config = create_dynamic_theme(draft.color_palette, theme_name="Custom Palette")
    
    # 2. Check for logo-based colors
    elif draft.logo_path and not draft.use_default_colors:
        extracted_colors = extract_colors_from_image(draft.logo_path)
        if extracted_colors:
            theme_config = create_dynamic_theme(extracted_colors, theme_name="Logo Derived")
    
    # 3. Fallback to default theme
    if not theme_config:
        theme_config = get_theme_config(Theme(draft.theme))
        
    colors = theme_config.colors
    fonts = theme_config.fonts

    # Standard Margins and Sizing (Presenton uses 1280x720 internal units)
    WIDTH = 1280
    HEIGHT = 720
    
    # --- Title Slide (premium: larger, bolder) ---
    title_slide = PptxSlideModel(
        background=PptxFillModel(color=colors.background),
        shapes=[
            PptxTextBoxModel(
                position=PptxPositionModel(left=80, top=200, width=1120, height=200),
                paragraphs=[
                    PptxParagraphModel(
                        text=draft.title,
                        font=PptxFontModel(
                            size=80,
                            font_weight=700,
                            name=fonts.header,
                            color=colors.primary
                        ),
                        alignment=PP_ALIGN.CENTER
                    )
                ],
                text_wrap=True
            ),
            PptxTextBoxModel(
                position=PptxPositionModel(left=80, top=460, width=1120, height=80),
                paragraphs=[
                    PptxParagraphModel(
                        text="POWERED BY SPARK2SCALE AI",
                        font=PptxFontModel(
                            size=24,
                            font_weight=600,
                            name=fonts.body,
                            color=colors.accent
                        ),
                        alignment=PP_ALIGN.CENTER
                    )
                ]
            )
        ]
    )

    # Add Logo to Title Slide if provided
    if draft.logo_path:
        title_slide.shapes.append(
            PptxPictureBoxModel(
                position=PptxPositionModel(left=50, top=50, width=150, height=100),
                picture=PptxPictureModel(path=draft.logo_path, is_network=False),
                object_fit=PptxObjectFitModel(fit=PptxObjectFitEnum.CONTAIN)
            )
        )
    
    slides.append(title_slide)
    
    # --- Content Slides ---
    for section in draft.sections:
        shapes = []
        
        # 1. Slide Title (premium: bigger, bolder)
        shapes.append(
            PptxTextBoxModel(
                position=PptxPositionModel(left=60, top=40, width=1160, height=100),
                paragraphs=[
                    PptxParagraphModel(
                        text=section.title.upper(),
                        font=PptxFontModel(
                            size=54,
                            font_weight=800,
                            name=fonts.header,
                            color=colors.primary
                        )
                    )
                ]
            )
        )
        
        # 2. Determine Layout
        has_visual = bool(section.image_path or section.visualization_path)
        
        if has_visual:
            # Split Layout: Text (Left) + Image/Chart (Right)
            asset_path = section.visualization_path if section.visualization_path else section.image_path
            
            # Text Cards (premium: bigger body; bold runs use accent color)
            card_width = 560
            body_font = PptxFontModel(size=28, name=fonts.body, color=colors.text_primary)
            highlight_font = PptxFontModel(size=28, name=fonts.body, color=colors.accent, font_weight=700)
            for i, bullet in enumerate(section.content[:3]):
                card_y = 160 + (i * 165)
                shapes.append(
                    PptxTextBoxModel(
                        position=PptxPositionModel(left=60, top=card_y, width=card_width, height=155),
                        paragraphs=[
                            PptxParagraphModel(
                                text=bullet,
                                font=body_font,
                                highlight_font=highlight_font
                            )
                        ]
                    )
                )

            # Large Image/Chart Card (Right side)
            shapes.append(
                PptxPictureBoxModel(
                    position=PptxPositionModel(left=660, top=160, width=560, height=480),
                    picture=PptxPictureModel(
                        path=asset_path,
                        is_network=False
                    ),
                    border_radius=[20, 20, 20, 20],
                    object_fit=PptxObjectFitModel(fit=PptxObjectFitEnum.COVER)
                )
            )
        else:
            # Full Width 3-Column (premium: bigger body; bold = accent color)
            col_width = 360
            body_font = PptxFontModel(size=32, name=fonts.body, color=colors.text_primary)
            highlight_font = PptxFontModel(size=32, name=fonts.body, color=colors.accent, font_weight=700)
            for i, bullet in enumerate(section.content[:3]):
                col_x = 60 + (i * 400)
                shapes.append(
                    PptxTextBoxModel(
                        position=PptxPositionModel(left=col_x, top=200, width=col_width, height=450),
                        paragraphs=[
                            PptxParagraphModel(
                                text=bullet,
                                font=body_font,
                                highlight_font=highlight_font,
                                alignment=PP_ALIGN.CENTER
                            )
                        ]
                    )
                )
        
        # Add Logo Watermark to Slide (Top Right)
        if draft.logo_path:
            shapes.append(
                PptxPictureBoxModel(
                    position=PptxPositionModel(left=1100, top=30, width=120, height=80),
                    picture=PptxPictureModel(path=draft.logo_path, is_network=False),
                    object_fit=PptxObjectFitModel(fit=PptxObjectFitEnum.CONTAIN)
                )
            )
                
        slide = PptxSlideModel(
            background=PptxFillModel(color=colors.background),
            shapes=shapes,
            note=section.speaker_notes or ""
        )
        slides.append(slide)
        
    return PptxPresentationModel(
        name=draft.title,
        slides=slides
    )


async def generate_pptx_file(draft: PPTDraft, output_path: str) -> str:
    """
    Generates a PPTX file from a PPTDraft object using the Presenton engine.
    """
    temp_dir = os.path.dirname(output_path)
    if temp_dir and not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # 1. Resolve Theme early (to use for charts)
    theme_config = None
    if draft.color_palette and not draft.use_default_colors:
        theme_config = create_dynamic_theme(draft.color_palette, theme_name="Custom Palette")
    elif draft.logo_path and not draft.use_default_colors:
        extracted_colors = extract_colors_from_image(draft.logo_path)
        if extracted_colors:
            theme_config = create_dynamic_theme(extracted_colors, theme_name="Logo Derived")
    if not theme_config:
        theme_config = get_theme_config(Theme(draft.theme))
    
    c = theme_config.colors
    # Matplotlib needs '#' prefix, but ThemeConfig uses bare hex for python-pptx
    chart_palette = [f"#{c.primary}", f"#{c.secondary}", f"#{c.accent}", f"#{c.text_secondary}", f"#{c.text_primary}"]
    font_name = theme_config.fonts.header

    # 2. Generate Assets (Images & Charts)
    logger.info("Generating assets for presentation...")
    for i, section in enumerate(draft.sections):
        # Image Generation
        if section.image_prompt:
            if not section.image_path or not os.path.exists(section.image_path):
                logger.info(f"Generating image for slide {i+1}: {section.image_prompt}")
                loop = asyncio.get_event_loop()
                image_path = await loop.run_in_executor(None, generate_image, section.image_prompt, temp_dir)
                section.image_path = image_path
        
        # Chart Generation: Pass theme colors and font!
        if section.visualization_data:
            if not section.visualization_path or not os.path.exists(section.visualization_path):
                logger.info(f"Generating theme-coherent chart for slide {i+1}")
                loop = asyncio.get_event_loop()
                chart_path = await loop.run_in_executor(None, generate_chart, section.visualization_data, temp_dir, chart_palette, font_name)
                section.visualization_path = chart_path

    # 2. Map simplified Draft -> Complex PptxModel
    pptx_model = map_draft_to_pptx_model(draft)
    
    # 3. Initialize Creator
    creator = PptxPresentationCreator(pptx_model, temp_dir)
    
    # 4. Create and Save
    await creator.create_ppt()
    creator.save(output_path)
    
    return output_path
