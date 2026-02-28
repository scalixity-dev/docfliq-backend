"""Shared domain exception classes for the course service.

These are raised by service-layer code and caught by controllers
to map to appropriate HTTP responses.
"""


class CourseNotFoundError(Exception):
    """Raised when a course cannot be found by ID or slug."""

    def __init__(self, identifier: str = ""):
        self.identifier = identifier
        super().__init__(f"Course not found: {identifier}")


class ModuleNotFoundError(Exception):
    def __init__(self, module_id: str = ""):
        self.module_id = module_id
        super().__init__(f"Module not found: {module_id}")


class LessonNotFoundError(Exception):
    def __init__(self, lesson_id: str = ""):
        self.lesson_id = lesson_id
        super().__init__(f"Lesson not found: {lesson_id}")


class EnrollmentNotFoundError(Exception):
    def __init__(self, identifier: str = ""):
        self.identifier = identifier
        super().__init__(f"Enrollment not found: {identifier}")


class QuizNotFoundError(Exception):
    def __init__(self, quiz_id: str = ""):
        self.quiz_id = quiz_id
        super().__init__(f"Quiz not found: {quiz_id}")


class CertificateNotFoundError(Exception):
    def __init__(self, identifier: str = ""):
        self.identifier = identifier
        super().__init__(f"Certificate not found: {identifier}")


class AlreadyEnrolledError(Exception):
    """Raised when user tries to enroll in a course they are already enrolled in."""


class NotEnrolledError(Exception):
    """Raised when an operation requires an active enrollment that does not exist."""


class CourseNotPublishedError(Exception):
    """Raised when enrollment is attempted on a non-PUBLISHED course."""


class PaymentRequiredError(Exception):
    """Raised when enrolling in a PAID course without a valid payment_id."""


class NotCourseOwnerError(Exception):
    """Raised when a non-instructor tries to modify a course they don't own."""


class InvalidStatusTransitionError(Exception):
    """Raised when a course status transition is not allowed."""

    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from {current} to {target}")


class QuizAlreadyExistsError(Exception):
    """Raised when trying to create a quiz for a lesson that already has one."""


class MaxAttemptsReachedError(Exception):
    """Raised when user has exhausted quiz attempt limit."""


class CourseNotCompletedError(Exception):
    """Raised when certificate generation is attempted before course completion."""


class CertificateAlreadyIssuedError(Exception):
    """Raised when a certificate has already been issued for this enrollment."""


class RefundNotEligibleError(Exception):
    """Raised when refund conditions are not met (<20% complete, within 7 days)."""


class ContentNotAccessibleError(Exception):
    """Raised when user tries to access content without enrollment or payment."""


class ScormSessionNotFoundError(Exception):
    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        super().__init__(f"SCORM session not found: {session_id}")


class ScormSessionAlreadyCompletedError(Exception):
    """Raised when trying to update a completed SCORM session."""


class QuizTimeLimitExceededError(Exception):
    """Raised when quiz submission exceeds the time limit."""


class CloudFrontSigningError(Exception):
    """Raised when CloudFront URL signing fails (missing key, config error)."""


class SelfRegistrationDisabledError(Exception):
    """Raised when self-registration is disabled for a course."""


class InvalidAccessCodeError(Exception):
    """Raised when the provided access code does not match."""


class InvalidPromoCodeError(Exception):
    """Raised when a promo code is invalid, expired, or exhausted."""


class LessonGatedError(Exception):
    """Raised when user tries to access a gated lesson without completing prerequisites."""

    def __init__(self, lesson_id: str = ""):
        self.lesson_id = lesson_id
        super().__init__(f"Complete previous lessons to unlock this content: {lesson_id}")


class EnrollmentPendingApprovalError(Exception):
    """Raised when enrollment is pending instructor approval."""


class SurveyNotFoundError(Exception):
    def __init__(self, survey_id: str = ""):
        self.survey_id = survey_id
        super().__init__(f"Survey not found: {survey_id}")


class SurveyAlreadyRespondedError(Exception):
    """Raised when user has already submitted a response for this survey."""


class ScormImportError(Exception):
    """Raised when SCORM package import fails."""


class PromoCodeNotFoundError(Exception):
    def __init__(self, identifier: str = ""):
        self.identifier = identifier
        super().__init__(f"Promo code not found: {identifier}")


class ModuleLockedError(Exception):
    """Raised when user tries to access a module that is locked by prerequisites."""

    def __init__(self, module_id: str = ""):
        self.module_id = module_id
        super().__init__(f"Module is locked: {module_id}")


class ModuleCertificateAlreadyIssuedError(Exception):
    """Raised when a module certificate has already been issued for this enrollment."""


class CertificationDisabledError(Exception):
    """Raised when certification is disabled for this course or module."""


class InvalidDependencyGraphError(Exception):
    """Raised when module dependency graph contains a cycle or invalid references."""

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(f"Invalid dependency graph: {detail}")
