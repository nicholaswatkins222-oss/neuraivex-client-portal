from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime

from extensions import db, limiter
from models import Course, Lesson, LessonProgress

courses_bp = Blueprint('courses', __name__)


@courses_bp.route('/courses')
@login_required
def index():
    courses = Course.query.filter_by(is_published=True).order_by(Course.order_index).all()
    course_data = []
    for course in courses:
        lessons = course.lessons.all()
        total = len(lessons)
        completed = 0
        if total:
            lesson_ids = [l.id for l in lessons]
            completed = LessonProgress.query.filter(
                LessonProgress.client_id == current_user.id,
                LessonProgress.lesson_id.in_(lesson_ids),
                LessonProgress.completed == True,
            ).count()
        progress_pct = int((completed / total) * 100) if total else 0
        course_data.append({
            'course': course,
            'total': total,
            'completed': completed,
            'progress_pct': progress_pct,
        })
    return render_template('courses.html', course_data=course_data)


@courses_bp.route('/courses/<int:course_id>')
@login_required
def detail(course_id):
    course = Course.query.filter_by(id=course_id, is_published=True).first_or_404()
    lessons = course.lessons.all()

    # Build completion map
    lesson_ids = [l.id for l in lessons]
    progress_records = LessonProgress.query.filter(
        LessonProgress.client_id == current_user.id,
        LessonProgress.lesson_id.in_(lesson_ids),
    ).all() if lesson_ids else []
    completed_ids = {p.lesson_id for p in progress_records if p.completed}

    total = len(lessons)
    completed_count = len(completed_ids)
    progress_pct = int((completed_count / total) * 100) if total else 0

    lesson_data = [{'lesson': l, 'completed': l.id in completed_ids} for l in lessons]
    return render_template(
        'course_detail.html',
        course=course,
        lesson_data=lesson_data,
        progress_pct=progress_pct,
        completed_count=completed_count,
        total=total,
    )


@courses_bp.route('/courses/<int:course_id>/lesson/<int:lesson_id>/complete', methods=['POST'])
@login_required
@limiter.limit('30 per minute')
def toggle_complete(course_id, lesson_id):
    course = Course.query.filter_by(id=course_id, is_published=True).first_or_404()
    lesson = Lesson.query.filter_by(id=lesson_id, course_id=course_id).first_or_404()

    record = LessonProgress.query.filter_by(
        client_id=current_user.id,
        lesson_id=lesson_id,
    ).first()

    if record:
        record.completed = not record.completed
        record.completed_at = datetime.utcnow() if record.completed else None
    else:
        record = LessonProgress(
            client_id=current_user.id,
            lesson_id=lesson_id,
            completed=True,
            completed_at=datetime.utcnow(),
        )
        db.session.add(record)

    db.session.commit()
    return jsonify({'completed': record.completed})
