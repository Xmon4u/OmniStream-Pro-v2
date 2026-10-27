#pragma once

#include <QMainWindow>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QComboBox>
#include <QPushButton>
#include <QProgressBar>
#include <QLabel>
#include <QCheckBox>
#include <QTableWidget>
#include <QStackedWidget>
#include <QMouseEvent>
#include <QPaintEvent>
#include <QPainter>
#include <QTimer>
#include <QMenu>
#include <QAction>
#include <QInputDialog>
#include <QMessageBox>
#include <QDesktopServices>
#include <QUrl>
#include <QClipboard>
#include <QProcess>
#include <QDir>
#include <QFileInfo>
#include <QSettings>
#include <QStandardPaths>
#include <cmath>
#include <memory>
#include <atomic>
#include <thread>
#include "download_engine.hpp"
#include "bridge_server.hpp"

namespace OmniStream {

// Custom Widget to render subtle cyber blueprint grid background
class EmptyQueueGridWidget : public QWidget {
    Q_OBJECT
public:
    explicit EmptyQueueGridWidget(QWidget *parent = nullptr) : QWidget(parent) {}
protected:
    void paintEvent(QPaintEvent *event) override {
        Q_UNUSED(event);
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        p.fillRect(rect(), QColor("#090d13"));

        // Draw subtle cyber grid
        p.setPen(QPen(QColor(25, 33, 44, 180), 1, Qt::DotLine));
        const int step = 20;
        for (int x = 0; x < width(); x += step) {
            p.drawLine(x, 0, x, height());
        }
        for (int y = 0; y < height(); y += step) {
            p.drawLine(0, y, width(), y);
        }

        // Draw rounded border with cyber glow
        p.setPen(QPen(QColor(56, 189, 248, 55), 1.2));
        p.drawRoundedRect(rect().adjusted(1, 1, -2, -2), 8, 8);
    }
};

enum class CaptionType {
    Minimize,
    Maximize,
    Close
};

class CaptionButton : public QPushButton {
    Q_OBJECT
public:
    CaptionButton(CaptionType type, QWidget* parent = nullptr)
        : QPushButton(parent), m_type(type) {
        setFixedSize(36, 26);
        setCursor(Qt::PointingHandCursor);
        setAttribute(Qt::WA_Hover, true);
    }

    void setMaximizedState(bool max) {
        if (m_isMaximized != max) {
            m_isMaximized = max;
            update();
        }
    }

protected:
    void paintEvent(QPaintEvent* event) override {
        Q_UNUSED(event);
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);

        bool isHover = underMouse();
        bool pressed = isDown();

        QRectF r = rect();
        r.adjust(0.5, 0.5, -0.5, -0.5);

        QColor bgColor = Qt::transparent;
        QColor borderColor = Qt::transparent;
        QColor iconColor = QColor("#94a3b8");

        if (m_type == CaptionType::Close) {
            if (pressed) {
                bgColor = QColor("#9f1239");
                borderColor = QColor("#be123c");
                iconColor = Qt::white;
            } else if (isHover) {
                bgColor = QColor("#e11d48");
                borderColor = QColor("#fb7185");
                iconColor = Qt::white;
            } else {
                bgColor = QColor(255, 255, 255, 6);
                borderColor = QColor(255, 255, 255, 12);
                iconColor = QColor("#94a3b8");
            }
        } else {
            if (pressed) {
                bgColor = QColor(30, 41, 59, 240);
                borderColor = QColor(56, 189, 248, 120);
                iconColor = QColor("#38bdf8");
            } else if (isHover) {
                bgColor = QColor(30, 41, 59, 180);
                borderColor = (m_type == CaptionType::Minimize) ? QColor(56, 189, 248, 90) : QColor(129, 140, 248, 90);
                iconColor = (m_type == CaptionType::Minimize) ? QColor("#38bdf8") : QColor("#818cf8");
            } else {
                bgColor = QColor(255, 255, 255, 6);
                borderColor = QColor(255, 255, 255, 12);
                iconColor = QColor("#94a3b8");
            }
        }

        // Draw luxury rounded pill container
        p.setBrush(bgColor);
        p.setPen(QPen(borderColor, 1.0));
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5.0, 5.0);

        // Draw crisp vector icon
        QPen iconPen(iconColor, 1.35f, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin);
        p.setPen(iconPen);
        p.setBrush(Qt::NoBrush);

        qreal cx = width() / 2.0;
        qreal cy = height() / 2.0;

        if (m_type == CaptionType::Minimize) {
            // Sleek horizontal bar (width 10px)
            p.drawLine(QPointF(cx - 5.0, cy), QPointF(cx + 5.0, cy));
        } else if (m_type == CaptionType::Maximize) {
            if (m_isMaximized) {
                // Restore icon: two overlapping sleek rectangles
                QRectF rBack(cx - 2.5, cy - 4.5, 7.5, 7.5);
                p.drawRoundedRect(rBack, 1.0, 1.0);

                QRectF rFront(cx - 5.0, cy - 2.0, 7.5, 7.5);
                p.fillRect(rFront, isHover ? bgColor : QColor("#090d13"));
                p.drawRoundedRect(rFront, 1.0, 1.0);
            } else {
                // Maximize icon: single square
                QRectF rBox(cx - 5.0, cy - 5.0, 10.0, 10.0);
                p.drawRoundedRect(rBox, 1.2, 1.2);
            }
        } else if (m_type == CaptionType::Close) {
            // Sleek diagonal cross
            qreal sz = 4.2;
            p.drawLine(QPointF(cx - sz, cy - sz), QPointF(cx + sz, cy + sz));
            p.drawLine(QPointF(cx + sz, cy - sz), QPointF(cx - sz, cy + sz));
        }
    }

private:
    CaptionType m_type;
    bool m_isMaximized = false;
};

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override;

signals:
    void logMessageReceived(const QString& msg);
    void progressUpdated(float pct, const QString& speed, const QString& eta, quint64 bytes, const QString& sizeStr);
    void downloadCompleted(bool success, const QString& finalPath = QString(), int queueIdx = -1);

protected:
    void paintEvent(QPaintEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void changeEvent(QEvent *event) override;
    void keyPressEvent(QKeyEvent *event) override;

private slots:
    void onPasteClicked();
    void onBrowseClicked();
    void onStartDownloadClicked();
    void onDownloadSubtitlesClicked();
    void onStopClicked();
    void onTabQueueClicked();
    void onTabTerminalClicked();
    void onDownloadAllClicked();
    void onPauseAllClicked();
    void onResumeAllClicked();
    void onStopAllClicked();
    void onClearQueueClicked();
    void onClearLogsClicked();
    void onFullViewClicked();
    void onThemeChanged(int index);
    void onDownloadModeChanged(int modeIdx);
    void setDownloadMode(const QString& modeStr);
    void handleLogMessage(const QString& msg);
    void handleProgressUpdate(float pct, const QString& speed, const QString& eta, quint64 bytes, const QString& sizeStr);
    void handleDownloadComplete(bool success, const QString& finalPath = QString(), int queueIdx = -1);
    void handleItemProgress(int row, float pct, const QString& speed, const QString& eta, quint64 bytes, const QString& sizeStr);
    void handleItemComplete(int row, bool success, const QString& finalPath = QString());
    void showQueueContextMenu(const QPoint& pos);
    void pauseQueueItem(int row);
    void resumeQueueItem(int row);
    void restartQueueItem(int row);
    void stopQueueItem(int row);
    void startQueueItem(int row, bool subtitleOnly = false);
    void playQueueItemFile(int row);
    void openQueueItemLocation(int row);
    void renameQueueItemTitle(int row);
    void copyQueueItemUrl(int row);
    void copyQueueItemFilePath(int row);
    void deleteQueueItemFile(int row);
    void removeQueueItem(int row);
    void updateQueueStats();

private:
    void setupUI();
    void applyStyleSheet(int themeIdx = 0);
    void startDownloadEngine(bool subtitleOnly);
    void addQueueItem(const DownloadOptions& opts);

    // Frameless window dragging state
    bool m_isDragging = false;
    QPoint m_dragPosition;

    // Top Header Widgets
    QLabel* m_lblLogo = nullptr;
    QLabel* m_lblTitle = nullptr;
    QLabel* m_lblVersionBadge = nullptr;
    QComboBox* m_comboTheme = nullptr;
    QLabel* m_lblStatusBadge = nullptr;

    // Window Caption Controls
    CaptionButton* m_btnCapMin = nullptr;
    CaptionButton* m_btnCapMax = nullptr;
    CaptionButton* m_btnCapClose = nullptr;

    // Banner Widget
    QWidget* m_bannerWidget = nullptr;

    // Card 1: Stream Source
    QWidget* m_card1 = nullptr;
    QPlainTextEdit* m_editUrl = nullptr;
    QPushButton* m_btnPaste = nullptr;

    // Card 2: Configuration Options
    QWidget* m_card2 = nullptr;
    QLineEdit* m_editTitle = nullptr;
    QComboBox* m_comboRes = nullptr;
    QLineEdit* m_editDir = nullptr;
    QPushButton* m_btnBrowse = nullptr;
    QComboBox* m_comboAudio = nullptr;
    QComboBox* m_comboSubFormat = nullptr;
    QComboBox* m_comboSubLang = nullptr;
    QCheckBox* m_checkEmbedSubs = nullptr;

    // Download Mode Segmented Buttons
    QPushButton* m_btnModeNormal = nullptr;
    QPushButton* m_btnModeTitleOnly = nullptr;
    QPushButton* m_btnModeImdb = nullptr;
    QPushButton* m_btnModeTmdb = nullptr;
    QPushButton* m_btnModeTitleId = nullptr;
    QPushButton* m_btnModeSubMerge = nullptr;
    int m_selectedMode = 0;

    // Action Buttons
    QWidget* m_actionWidget = nullptr;
    QPushButton* m_btnStart = nullptr;
    QPushButton* m_btnSubs = nullptr;
    QPushButton* m_btnStop = nullptr;

    // Card 3: Progress Card
    QWidget* m_card3 = nullptr;
    QLabel* m_lblProgTitle = nullptr;
    QLabel* m_lblProgStatus = nullptr;
    QLabel* m_lblProgPct = nullptr;
    QProgressBar* m_progBar = nullptr;
    QLabel* m_lblProgSize = nullptr;
    QLabel* m_lblProgSpeed = nullptr;
    bool m_isFullView = false;

    // Card 4: Tab Container & Views
    QPushButton* m_btnTabQueue = nullptr;
    QPushButton* m_btnTabTerminal = nullptr;
    QPushButton* m_btnDownloadAll = nullptr;
    QPushButton* m_btnPauseAll = nullptr;
    QPushButton* m_btnResumeAll = nullptr;
    QPushButton* m_btnStopAll = nullptr;
    QPushButton* m_btnClearQueue = nullptr;
    QPushButton* m_btnFullView = nullptr;
    QLabel* m_lblQueueStats = nullptr;
    QPushButton* m_btnClearLogs = nullptr;

    QStackedWidget* m_stackedPages = nullptr;
    QWidget* m_pageQueue = nullptr;
    EmptyQueueGridWidget* m_emptyQueuePlaceholder = nullptr;
    QTableWidget* m_tableQueue = nullptr;
    QPlainTextEdit* m_editTerminal = nullptr;

    // Footer
    QLabel* m_lblFooterBridge = nullptr;
    QLabel* m_lblFooterAuthor = nullptr;

    // Animation and visual effects
    QTimer* m_animTimer = nullptr;
    float m_glowAngle = 0.0f;
    float m_pulseValue = 0.0f;

    // Backend Core
    struct QueueEntry {
        DownloadOptions options;
        QString status = "Queued"; // "Queued", "Downloading", "Paused", "Stopped", "Done", "Failed", "Cancelled"
        QString downloadedSize = "--";
        QString filePath;
        float progressPercent = 0.0f;
        QString speed = "--";
        QString eta = "--";
        std::shared_ptr<DownloadEngine> engine;
    };
    std::vector<QueueEntry> m_queueItems;
    int m_activeQueueIndex = -1;

    std::unique_ptr<BridgeServer> m_bridgeServer;
    std::shared_ptr<DownloadEngine> m_currentEngine;
    std::atomic<bool> m_isDownloading{ false };
};

} // namespace OmniStream
