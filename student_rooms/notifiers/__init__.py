"""Pluggable notification backends for student-rooms-cli."""

from student_rooms.notifiers.base import BaseNotifier, create_notifier

__all__ = ["BaseNotifier", "create_notifier"]
