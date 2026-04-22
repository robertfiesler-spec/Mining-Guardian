#!/usr/bin/env python3
"""
PDF Report Builder for Mining Guardian
Generates weekly/daily PDF reports with fleet status, issues, and AI insights.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "guardian.db"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Brand colors
PRIMARY_COLOR = HexColor("#1a1a2e")
ACCENT_COLOR = HexColor("#f39c12")
SUCCESS_COLOR = HexColor("#27ae60")
WARNING_COLOR = HexColor("#e67e22")
DANGER_COLOR = HexColor("#e74c3c")


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_fleet_summary(days: int = 7) -> Dict:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    with get_db() as conn:
        latest = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        
        stats = conn.execute("""
            SELECT 
                AVG(total_miners) as avg_miners,
                AVG(online) as avg_online,
                AVG(offline) as avg_offline,
                AVG(issues) as avg_issues,
                COUNT(*) as total_scans
            FROM scans WHERE scanned_at >= ?
        """, (cutoff,)).fetchone()
        
        issues = conn.execute("""
            SELECT COUNT(*) as count FROM miner_readings
            WHERE scanned_at >= ? AND action IS NOT NULL AND action != "MONITOR"
        """, (cutoff,)).fetchone()
        
        actions = conn.execute("""
            SELECT action_taken as action, COUNT(*) as count
            FROM action_audit_log WHERE timestamp >= ?
            GROUP BY action_taken ORDER BY count DESC
        """, (cutoff,)).fetchall()
        
    return {
        "latest": dict(latest) if latest else {},
        "stats": dict(stats) if stats else {},
        "issues_flagged": issues["count"] if issues else 0,
        "actions": [dict(a) for a in actions]
    }


def get_top_issues(days: int = 7, limit: int = 10) -> List[Dict]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    with get_db() as conn:
        issues = conn.execute("""
            SELECT issue, COUNT(*) as occurrences, COUNT(DISTINCT miner_id) as affected_miners
            FROM miner_readings
            WHERE scanned_at >= ? AND issue IS NOT NULL AND issue != ""
            GROUP BY issue ORDER BY occurrences DESC LIMIT ?
        """, (cutoff, limit)).fetchall()
        
    return [dict(i) for i in issues]


def get_miner_rankings(limit: int = 10) -> Dict:
    with get_db() as conn:
        worst = conn.execute("""
            SELECT miner_id, ip, model, COUNT(*) as issue_count
            FROM miner_readings
            WHERE action IS NOT NULL AND action != "MONITOR"
            AND scanned_at >= datetime("now", "-7 days")
            GROUP BY miner_id ORDER BY issue_count DESC LIMIT ?
        """, (limit,)).fetchall()
        
        best = conn.execute("""
            SELECT miner_id, ip, model, AVG(hashrate_pct) as avg_efficiency
            FROM miner_readings
            WHERE scanned_at >= datetime("now", "-7 days") AND status = "online"
            GROUP BY miner_id HAVING COUNT(*) > 5
            ORDER BY avg_efficiency DESC LIMIT ?
        """, (limit,)).fetchall()
        
    return {"worst": [dict(w) for w in worst], "best": [dict(b) for b in best]}


def get_predictor_alerts() -> List[Dict]:
    """Get current predictor warnings from latest scan."""
    try:
        from ai.predictor import run_predictions, get_db
        
        # Get latest scan_id
        with get_db() as conn:
            row = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return []
            scan_id = row[0]
        
        # Run predictions
        predictions = run_predictions(scan_id)
        
        # Sort by score, top 10
        sorted_preds = sorted(predictions, key=lambda x: x.get('confidence', 0), reverse=True)[:10]
        
        return sorted_preds
    except Exception as e:
        logger.warning(f"Could not get predictor data: {e}")
        return []


def get_ai_insights() -> Dict:
    knowledge_path = Path(__file__).parent.parent / "knowledge.json"
    if not knowledge_path.exists():
        return {}
    
    try:
        with open(knowledge_path) as f:
            knowledge = json.load(f)
        
        return {
            "total_miners": len(knowledge.get("miner_fingerprints", {})),
            "known_issues": len(knowledge.get("known_issues", [])),
            "patterns": len(knowledge.get("behavioral_patterns", [])),
            "recent_learnings": knowledge.get("recent_learnings", [])[:5]
        }
    except Exception as e:
        logger.warning(f"Could not load knowledge: {e}")
        return {}


def get_maintenance_history(days: int = 7) -> List[Dict]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    with get_db() as conn:
        windows = conn.execute("""
            SELECT * FROM maintenance_windows
            WHERE created_at >= ? OR end_time >= ?
            ORDER BY start_time DESC LIMIT 10
        """, (cutoff, cutoff)).fetchall()
        
    return [dict(w) for w in windows]


def create_report_styles():
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Heading1"],
        fontSize=24, spaceAfter=30, textColor=PRIMARY_COLOR, alignment=TA_CENTER
    ))
    
    styles.add(ParagraphStyle(
        name="SectionHeader", parent=styles["Heading2"],
        fontSize=16, spaceBefore=20, spaceAfter=10, textColor=PRIMARY_COLOR
    ))
    
    styles.add(ParagraphStyle(
        name="SubHeader", parent=styles["Heading3"],
        fontSize=12, spaceBefore=15, spaceAfter=5, textColor=PRIMARY_COLOR
    ))
    
    styles.add(ParagraphStyle(
        name="ReportBody", parent=styles["Normal"],
        fontSize=10, spaceAfter=6, leading=14
    ))
    
    styles.add(ParagraphStyle(
        name="SmallText", parent=styles["Normal"],
        fontSize=8, textColor=HexColor("#666666")
    ))
    
    return styles


def generate_weekly_report(days: int = 7, output_path: Optional[Path] = None) -> Path:
    if output_path is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = REPORTS_DIR / f"weekly_report_{timestamp}.pdf"
    
    styles = create_report_styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=letter,
        rightMargin=0.75*inch, leftMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch
    )
    
    story = []
    
    # Title
    story.append(Paragraph("Mining Guardian Weekly Report", styles["ReportTitle"]))
    story.append(Paragraph(
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
        styles["SmallText"]
    ))
    story.append(Paragraph(f"Period: Last {days} days", styles["SmallText"]))
    story.append(Spacer(1, 20))
    
    # Fleet Summary
    summary = get_fleet_summary(days)
    story.append(Paragraph("Fleet Summary", styles["SectionHeader"]))
    
    if summary["latest"]:
        latest = summary["latest"]
        stats = summary["stats"]
        
        data = [
            ["Metric", "Current", f"{days}-Day Avg"],
            ["Total Miners", str(latest.get("total_miners", "N/A")), f"{stats.get('avg_miners', 0):.1f}"],
            ["Online", str(latest.get("online", "N/A")), f"{stats.get('avg_online', 0):.1f}"],
            ["Offline", str(latest.get("offline", "N/A")), f"{stats.get('avg_offline', 0):.1f}"],
            ["Issues Flagged", str(latest.get("issues", "N/A")), f"{stats.get('avg_issues', 0):.1f}"],
        ]
        
        table = Table(data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor("#f8f9fa")),
            ("GRID", (0, 0), (-1, -1), 1, HexColor("#dee2e6")),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("TOPPADDING", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
        ]))
        story.append(table)
        story.append(Spacer(1, 10))
        
        if summary["actions"]:
            story.append(Paragraph("Actions Taken:", styles["SubHeader"]))
            actions_text = ", ".join([f"{a['action']}: {a['count']}" for a in summary["actions"][:5]])
            story.append(Paragraph(actions_text, styles["ReportBody"]))
    
    story.append(Spacer(1, 15))
    
    # Top Issues
    story.append(Paragraph("Top Issues", styles["SectionHeader"]))
    issues = get_top_issues(days)
    
    if issues:
        data = [["Issue", "Occurrences", "Miners Affected"]]
        for issue in issues[:8]:
            issue_text = issue["issue"][:50] + "..." if len(issue["issue"]) > 50 else issue["issue"]
            data.append([issue_text, str(issue["occurrences"]), str(issue["affected_miners"])])
        
        table = Table(data, colWidths=[4*inch, 1.25*inch, 1.25*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor("#f8f9fa")),
            ("GRID", (0, 0), (-1, -1), 1, HexColor("#dee2e6")),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No significant issues in this period.", styles["ReportBody"]))
    
    story.append(Spacer(1, 15))
    
    # Miner Rankings
    story.append(Paragraph("Miner Performance", styles["SectionHeader"]))
    rankings = get_miner_rankings()
    
    if rankings["worst"]:
        story.append(Paragraph("Most Problematic Miners:", styles["SubHeader"]))
        data = [["Miner ID", "IP", "Model", "Issues"]]
        for m in rankings["worst"][:5]:
            data.append([
                str(m["miner_id"]), m["ip"],
                m["model"][:15] if m["model"] else "N/A", str(m["issue_count"])
            ])
        
        table = Table(data, colWidths=[1.5*inch, 1.75*inch, 2*inch, 1*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DANGER_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor("#fdf2f2")),
            ("GRID", (0, 0), (-1, -1), 1, HexColor("#f5c6cb")),
        ]))
        story.append(table)
        story.append(Spacer(1, 10))
    
    if rankings["best"]:
        story.append(Paragraph("Top Performers:", styles["SubHeader"]))
        data = [["Miner ID", "IP", "Model", "Avg Efficiency"]]
        for m in rankings["best"][:5]:
            data.append([
                str(m["miner_id"]), m["ip"],
                m["model"][:15] if m["model"] else "N/A", f"{m['avg_efficiency']:.1f}%"
            ])
        
        table = Table(data, colWidths=[1.5*inch, 1.75*inch, 2*inch, 1*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SUCCESS_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor("#f0fff4")),
            ("GRID", (0, 0), (-1, -1), 1, HexColor("#c3e6cb")),
        ]))
        story.append(table)
    
    story.append(PageBreak())
    
    # Predictor Alerts
    story.append(Paragraph("Failure Predictions", styles["SectionHeader"]))
    alerts = get_predictor_alerts()
    
    if alerts:
        story.append(Paragraph(
            "The AI predictor has identified these miners as at-risk:",
            styles["ReportBody"]
        ))
        
        data = [["Miner", "Risk Score", "Top Signals"]]
        for a in alerts[:8]:
            signals = ", ".join(a.get("signals", [])[:2])
            data.append([
                f"{a.get('miner_id', 'N/A')} ({a.get('ip', '')})",
                f"{a.get('confidence', 0):.1f}",
                signals[:40] + "..." if len(signals) > 40 else signals
            ])
        
        table = Table(data, colWidths=[2.5*inch, 1*inch, 3*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), WARNING_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor("#fff8e1")),
            ("GRID", (0, 0), (-1, -1), 1, HexColor("#ffe0b2")),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No high-risk miners identified at this time.", styles["ReportBody"]))
    
    story.append(Spacer(1, 15))
    
    # AI Insights
    story.append(Paragraph("AI Learning Summary", styles["SectionHeader"]))
    insights = get_ai_insights()
    
    if insights:
        story.append(Paragraph(
            f"Mining Guardian has fingerprinted <b>{insights.get('total_miners', 0)}</b> miners, "
            f"learned <b>{insights.get('known_issues', 0)}</b> issue patterns, "
            f"and identified <b>{insights.get('patterns', 0)}</b> behavioral patterns.",
            styles["ReportBody"]
        ))
    else:
        story.append(Paragraph("AI learning data not available.", styles["ReportBody"]))
    
    story.append(Spacer(1, 15))
    
    # Maintenance
    story.append(Paragraph("Maintenance Windows", styles["SectionHeader"]))
    maintenance = get_maintenance_history(days)
    
    if maintenance:
        data = [["Title", "Start", "End", "Status"]]
        for m in maintenance[:5]:
            start = datetime.fromisoformat(m["start_time"]).strftime("%m/%d %H:%M")
            end = datetime.fromisoformat(m["end_time"]).strftime("%m/%d %H:%M")
            data.append([m["title"][:25], start, end, m["status"].capitalize()])
        
        table = Table(data, colWidths=[2.5*inch, 1.25*inch, 1.25*inch, 1.25*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor("#f8f9fa")),
            ("GRID", (0, 0), (-1, -1), 1, HexColor("#dee2e6")),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No maintenance windows in this period.", styles["ReportBody"]))
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph("Generated by Mining Guardian AI System", styles["SmallText"]))
    story.append(Paragraph("BiXBiT USA - Fort Worth, TX", styles["SmallText"]))
    
    doc.build(story)
    logger.info(f"Report generated: {output_path}")
    
    return output_path


def cmd_report(args: str = "") -> str:
    parts = args.strip().split() if args else []
    
    days = 7
    if parts and parts[0].isdigit():
        days = min(int(parts[0]), 30)
    
    try:
        report_path = generate_weekly_report(days=days)
        filename = report_path.name
        
        return (":page_facing_up: *Report Generated*\n\n"
                f"Period: Last {days} days\n"
                f"File: `{filename}`\n\n"
                f"Download: `https://dashboard.fieslerfamily.com/reports/{filename}`")
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return f":x: Report generation failed: {e}"


if __name__ == "__main__":
    print("Generating test report...")
    path = generate_weekly_report()
    print(f"Report saved to: {path}")
