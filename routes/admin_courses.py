from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from functools import wraps

from extensions import db
from models import Course, Lesson, LessonProgress
from sanitize import strip_html, check_length

admin_courses_bp = Blueprint('admin_courses', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Courses ──────────────────────────────────────────────────────────────────

@admin_courses_bp.route('/courses')
@login_required
@admin_required
def courses():
    all_courses = Course.query.order_by(Course.order_index).all()
    return render_template('admin/courses.html', courses=all_courses)


@admin_courses_bp.route('/courses/add', methods=['GET', 'POST'])
@login_required
@admin_required
def course_add():
    if request.method == 'POST':
        title = strip_html(request.form.get('title', '').strip())
        description = strip_html(request.form.get('description', '').strip()) or None
        thumbnail_url = request.form.get('thumbnail_url', '').strip() or None
        order_index = request.form.get('order_index', '0')
        is_published = request.form.get('is_published') == '1'

        if not title:
            flash('Title is required.', 'error')
            return render_template('admin/course_add.html')

        ok, err = check_length(title, 255, 'Title')
        if not ok:
            flash(err, 'error')
            return render_template('admin/course_add.html')

        try:
            order_index = int(order_index)
        except ValueError:
            order_index = 0

        course = Course(
            title=title,
            description=description,
            thumbnail_url=thumbnail_url,
            order_index=order_index,
            is_published=is_published,
        )
        db.session.add(course)
        db.session.commit()
        flash(f'Course "{title}" created.', 'success')
        return redirect(url_for('admin_courses.courses'))

    return render_template('admin/course_add.html')


@admin_courses_bp.route('/courses/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def course_edit(course_id):
    course = Course.query.get_or_404(course_id)

    if request.method == 'POST':
        title = strip_html(request.form.get('title', '').strip())
        description = strip_html(request.form.get('description', '').strip()) or None
        thumbnail_url = request.form.get('thumbnail_url', '').strip() or None
        order_index = request.form.get('order_index', '0')
        is_published = request.form.get('is_published') == '1'

        if not title:
            flash('Title is required.', 'error')
            return render_template('admin/course_edit.html', course=course)

        ok, err = check_length(title, 255, 'Title')
        if not ok:
            flash(err, 'error')
            return render_template('admin/course_edit.html', course=course)

        try:
            order_index = int(order_index)
        except ValueError:
            order_index = 0

        course.title = title
        course.description = description
        course.thumbnail_url = thumbnail_url
        course.order_index = order_index
        course.is_published = is_published
        db.session.commit()
        flash('Course updated.', 'success')
        return redirect(url_for('admin_courses.courses'))

    return render_template('admin/course_edit.html', course=course)


@admin_courses_bp.route('/courses/<int:course_id>/delete', methods=['POST'])
@login_required
@admin_required
def course_delete(course_id):
    course = Course.query.get_or_404(course_id)
    # Cascade: delete progress records then lessons
    for lesson in course.lessons.all():
        LessonProgress.query.filter_by(lesson_id=lesson.id).delete()
        db.session.delete(lesson)
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted.', 'success')
    return redirect(url_for('admin_courses.courses'))


# ── Lessons ───────────────────────────────────────────────────────────────────

@admin_courses_bp.route('/courses/<int:course_id>/lesson/add', methods=['GET', 'POST'])
@login_required
@admin_required
def lesson_add(course_id):
    course = Course.query.get_or_404(course_id)

    if request.method == 'POST':
        title = strip_html(request.form.get('title', '').strip())
        description = strip_html(request.form.get('description', '').strip()) or None
        video_url = request.form.get('video_url', '').strip() or None
        content = strip_html(request.form.get('content', '').strip()) or None
        order_index = request.form.get('order_index', '0')
        duration_minutes = request.form.get('duration_minutes', '').strip()

        if not title:
            flash('Title is required.', 'error')
            return render_template('admin/lesson_add.html', course=course)

        ok, err = check_length(title, 255, 'Title')
        if not ok:
            flash(err, 'error')
            return render_template('admin/lesson_add.html', course=course)

        if content:
            ok, err = check_length(content, 20000, 'Content')
            if not ok:
                flash(err, 'error')
                return render_template('admin/lesson_add.html', course=course)

        try:
            order_index = int(order_index)
        except ValueError:
            order_index = 0

        try:
            duration_minutes = int(duration_minutes) if duration_minutes else None
        except ValueError:
            duration_minutes = None

        lesson = Lesson(
            course_id=course_id,
            title=title,
            description=description,
            video_url=video_url,
            content=content,
            order_index=order_index,
            duration_minutes=duration_minutes,
        )
        db.session.add(lesson)
        db.session.commit()
        flash(f'Lesson "{title}" added.', 'success')
        return redirect(url_for('admin_courses.course_edit', course_id=course_id))

    return render_template('admin/lesson_add.html', course=course)


@admin_courses_bp.route('/lesson/<int:lesson_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def lesson_edit(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    course = lesson.course

    if request.method == 'POST':
        title = strip_html(request.form.get('title', '').strip())
        description = strip_html(request.form.get('description', '').strip()) or None
        video_url = request.form.get('video_url', '').strip() or None
        content = strip_html(request.form.get('content', '').strip()) or None
        order_index = request.form.get('order_index', '0')
        duration_minutes = request.form.get('duration_minutes', '').strip()

        if not title:
            flash('Title is required.', 'error')
            return render_template('admin/lesson_edit.html', lesson=lesson, course=course)

        ok, err = check_length(title, 255, 'Title')
        if not ok:
            flash(err, 'error')
            return render_template('admin/lesson_edit.html', lesson=lesson, course=course)

        if content:
            ok, err = check_length(content, 20000, 'Content')
            if not ok:
                flash(err, 'error')
                return render_template('admin/lesson_edit.html', lesson=lesson, course=course)

        try:
            order_index = int(order_index)
        except ValueError:
            order_index = 0

        try:
            duration_minutes = int(duration_minutes) if duration_minutes else None
        except ValueError:
            duration_minutes = None

        lesson.title = title
        lesson.description = description
        lesson.video_url = video_url
        lesson.content = content
        lesson.order_index = order_index
        lesson.duration_minutes = duration_minutes
        db.session.commit()
        flash('Lesson updated.', 'success')
        return redirect(url_for('admin_courses.course_edit', course_id=course.id))

    return render_template('admin/lesson_edit.html', lesson=lesson, course=course)


@admin_courses_bp.route('/lesson/<int:lesson_id>/delete', methods=['POST'])
@login_required
@admin_required
def lesson_delete(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    course_id = lesson.course_id
    LessonProgress.query.filter_by(lesson_id=lesson_id).delete()
    db.session.delete(lesson)
    db.session.commit()
    flash('Lesson deleted.', 'success')
    return redirect(url_for('admin_courses.course_edit', course_id=course_id))
