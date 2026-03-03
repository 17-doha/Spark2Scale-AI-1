"""
Output Manager for Recommendation Agent
Handles structured document saving with timestamps and unique IDs
"""
import os
import json
from datetime import datetime
from pathlib import Path
import uuid


class OutputManager:
    """Manages saving recommendation outputs to structured files"""
    
    def __init__(self, base_output_dir="output"):
        """
        Initialize the output manager
        
        Args:
            base_output_dir: Base directory for all outputs (default: "output")
        """
        self.base_output_dir = Path(base_output_dir)
        self.recommendations_dir = self.base_output_dir / "recommendations"
        
    def create_output_directories(self):
        """Create the output directory structure if it doesn't exist"""
        self.recommendations_dir.mkdir(parents=True, exist_ok=True)
        
    def generate_request_id(self):
        """Generate a unique request ID"""
        return str(uuid.uuid4())[:8]
        
    def get_timestamp(self):
        """Get current timestamp in ISO format"""
        return datetime.now().isoformat()
    
    def get_next_report_number(self):
        """
        Get the next sequential report number
        
        Returns:
            int: Next report number
        """
        if not self.recommendations_dir.exists():
            return 1
        
        # Find all existing report folders
        existing_reports = []
        for folder in self.recommendations_dir.iterdir():
            if folder.is_dir() and folder.name.startswith("report_"):
                try:
                    num = int(folder.name.split("_")[1])
                    existing_reports.append(num)
                except (ValueError, IndexError):
                    continue
        
        # Return next number
        return max(existing_reports) + 1 if existing_reports else 1
        
    def get_folder_name(self, request_id=None):
        """
        Generate a folder name with sequential report numbering
        
        Args:
            request_id: Optional request ID (not used, kept for compatibility)
            
        Returns:
            str: Folder name in format report_N
        """
        report_num = self.get_next_report_number()
        return f"report_{report_num}"
        
    def save_recommendation(self, recommendation_text, raw_input=None, eval_output=None, 
                          insights=None, patterns=None, refined_statements=None, 
                          market_signals=None, request_id=None, processing_time=None):
        """
        Save recommendation output in multiple formats
        
        Args:
            recommendation_text: The main recommendation report text
            raw_input: Original input data (optional)
            eval_output: Evaluation output data (optional)
            insights: Extracted insights (optional)
            patterns: Detected patterns (optional)
            refined_statements: AI-refined statements (optional)
            request_id: Request ID (will generate if not provided)
            processing_time: Processing time in seconds (optional)
            
        Returns:
            dict: Paths to saved files
        """
        # Ensure directories exist
        self.create_output_directories()
        
        # Generate request ID if not provided
        if request_id is None:
            request_id = self.generate_request_id()
            
        # Create unique folder for this recommendation
        folder_name = self.get_folder_name(request_id)
        output_folder = self.recommendations_dir / folder_name
        output_folder.mkdir(parents=True, exist_ok=True)
        
        timestamp = self.get_timestamp()
        
        # Prepare file paths
        json_path = output_folder / "recommendation.json"
        markdown_path = output_folder / "recommendation.md"
        metadata_path = output_folder / "metadata.json"
        
        # Save JSON structured data
        json_data = {
            "request_id": request_id,
            "timestamp": timestamp,
            "recommendation_report": recommendation_text,
            "insights": insights or {},
            "refined_statements": refined_statements or {},
            "patterns_detected": patterns or [],
            "market_signals": market_signals or {},
            "evaluation_scores": eval_output.get("scores") if eval_output else None,
            "company_context": eval_output.get("company_context") if eval_output else None,
            "stage": eval_output.get("stage") if eval_output else None
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
            
        # Save Markdown report
        markdown_content = self._format_markdown_report(
            recommendation_text, 
            insights, 
            eval_output,
            patterns,
            refined_statements,
            market_signals,
            request_id, 
            timestamp
        )
        
        with open(markdown_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
            
        # Save metadata
        metadata = {
            "request_id": request_id,
            "created_at": timestamp,
            "input_summary": self._get_input_summary(raw_input),
            "processing_time_seconds": processing_time,
            "status": "success",
            "output_files": {
                "json": str(json_path),
                "markdown": str(markdown_path)
            }
        }
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        # Return file paths
        return {
            "request_id": request_id,
            "folder": str(output_folder),
            "files": {
                "json": str(json_path),
                "markdown": str(markdown_path),
                "metadata": str(metadata_path)
            }
        }
        
    def _format_markdown_report(self, recommendation_text, insights, eval_output, 
                                patterns, refined_statements, market_signals, request_id, timestamp):
        """Format the recommendation as a markdown document with Spark2Scale branding and colors"""
        
        # Extract company name for header
        company_name = insights.get('company_name', 'Startup') if insights else 'Startup'
        
        # Parse the recommendation text to extract sections and reformat
        formatted_report = self._reformat_recommendation_text(recommendation_text, patterns)
        
        markdown = f"""<div style="font-family: 'Segoe UI', Arial, sans-serif; color: #2d3e1f; line-height: 1.5;">

# [LAUNCH] Spark2Scale Recommendation Agent

<div style="background: linear-gradient(135deg, #4a5f2d 0%, #7b8f4a 100%); color: white; padding: 15px; border-radius: 8px; margin: 15px 0;">

## Strategic Recommendations for **{company_name}**

</div>

<div style="border-left: 4px solid #7b8f4a; padding-left: 15px; margin: 15px 0; background-color: #f9faf6; padding: 10px; border-radius: 5px;">

### [DATA] Company Overview

"""
        
        # Add company info if available
        if insights:
            markdown += f"""
| Attribute | Details |
|-----------|---------|
| **Company Name** | <span style="color: #4a5f2d; font-weight: bold;">{insights.get('company_name', 'N/A')}</span> |
| **Stage** | <span style="color: #7b8f4a;">{insights.get('stage', 'N/A')}</span> |
| **Target Raise** | <span style="color: #a8b76d;">{insights.get('target_raise', 'N/A')}</span> |
| **Generated** | {datetime.fromisoformat(timestamp).strftime('%B %d, %Y at %I:%M %p')} |

</div>

<div style="page-break-after: always;"></div>

"""
        
        # Add refined statements section if available
        if refined_statements:
            markdown += f"""
---

<div style="background-color: #f9faf6; padding: 10px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #a8b76d;">

## <span style="color: #4a5f2d;">[REPORT] Statement Refinements</span>

**AI-Enhanced Core Messaging** — Improved versions of your key statements for better clarity and investor appeal.

| Category | Original Statement | Refined Statement | Why It's Better |
| :--- | :--- | :--- | :--- |
"""
            
            # Map of statement types to display with readable titles
            statement_types = [
                ("Problem Statement", "problem_statement"),
                ("Founder-Market Fit", "founder_market_fit"),
                ("Differentiation", "differentiation"),
                ("Core Stickiness", "core_stickiness"),
                ("Five-Year Vision", "five_year_vision"),
                ("Beachhead Market", "beachhead_market"),
                ("Gap Analysis", "gap_analysis")
            ]
            
            for title, key in statement_types:
                if key in refined_statements and isinstance(refined_statements[key], dict):
                    data = refined_statements[key]
                    original = data.get('original', 'N/A').replace('\n', ' ')
                    recommended = data.get('recommended', 'N/A').replace('\n', ' ')
                    why_better = data.get('why_better', '').replace('\n', ' ')
                    
                    markdown += f"| **{title}** | <span style='color: #666; font-style: italic;'>{original}</span> | <span style='color: #2d3e1f; font-weight: 500;'>{recommended}</span> | <span style='color: #555;'>{why_better}</span> |\n"
            
            markdown += """
</div>

<div style="page-break-after: always;"></div>

"""

        
        # Add main recommendation report
        markdown += f"""
---

## <span style="color: #4a5f2d;">📋 Strategic Analysis & Recommendations</span>

<div style="margin: 20px 0;">

{formatted_report}

</div>

---

<div style="page-break-before: always;"></div>

<div style="background-color: #f9faf6; padding: 20px; border-radius: 8px; border-left: 4px solid #4a5f2d; margin-top: 30px;">

## [IDEA] About This Report

This strategic recommendation report was generated by the **Spark2Scale AI Recommendation Agent** using advanced evaluation algorithms and AI-powered analysis. The recommendations are based on startup evaluation data, market research, and industry best practices.

<div style="color: #7b8f4a; font-style: italic; margin-top: 10px;">
[WARNING] **Note:** This is an automated analysis. Please use professional judgment when implementing these recommendations.
</div>

</div>

</div>
"""
        
        return markdown

    
    def _reformat_recommendation_text(self, text, patterns):
        """Reformat recommendation text to remove pattern IDs from tables and add styling"""
        
        # Split into lines
        lines = text.split('\n')
        formatted_lines = []
        in_table = False
        table_headers_found = False
        
        for line in lines:
            # Check if we're in the DETECTION & ACTION TABLE section
            if '| Pattern ID |' in line or '| :--- |' in line:
                # Skip the Pattern ID column header and separator
                if '| Pattern ID |' in line:
                    # Remove Pattern ID column from header
                    line = line.replace('| Pattern ID |', '|', 1)
                    in_table = True
                    table_headers_found = True
                elif '| :--- |' in line and in_table:
                    # Remove Pattern ID column from separator
                    line = line.replace('| :--- |', '|', 1)
            elif in_table and line.startswith('| **FP-'):
                # This is a data row - remove the Pattern ID column
                parts = line.split('|')
                if len(parts) >= 6:  # Has Pattern ID column
                    # Remove first column (empty) and second column (Pattern ID)
                    line = '|' + '|'.join(parts[2:])
            elif line.startswith('###') or line.startswith('##'):
                in_table = False
                # Add color styling to headers
                if '###' in line:
                    header_text = line.replace('###', '').strip()
                    line = f'### <span style="color: #4a5f2d;">{header_text}</span>'
                elif '##' in line:
                    header_text = line.replace('##', '').strip()
                    line = f'## <span style="color: #4a5f2d;">📋 {header_text}</span>'
            
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
        
    def _get_input_summary(self, raw_input):
        """Extract a summary from raw input data"""
        if not raw_input:
            return "No input summary available"
            
        if isinstance(raw_input, dict):
            startup_eval = raw_input.get("startup_evaluation", {})
            company_snapshot = startup_eval.get("company_snapshot", {})
            return {
                "company_name": company_snapshot.get("company_name", "Unknown"),
                "stage": company_snapshot.get("current_stage", "Unknown"),
                "founded": company_snapshot.get("date_founded", "Unknown")
            }
        elif isinstance(raw_input, str):
            return raw_input[:200] + "..." if len(raw_input) > 200 else raw_input
        else:
            return str(raw_input)[:200]
