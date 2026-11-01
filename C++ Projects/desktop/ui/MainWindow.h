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
#include <QScrollArea>
#include <QVBoxLayout>
#include <QHBoxLayout>
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
#include <QDir>
#include <QFileInfo>
#include <QSystemTrayIcon>
#include <cmath>
#include <memory>
#include <atomic>
#include <vector>
#include <unordered_map>

#include "Common.hpp"
#include "QueueManager.hpp"
#include "SettingsManager.hpp"
#include "BridgeServer.hpp"
#include "StreamResolver.hpp"
#include "MetadataResolver.hpp"

namespace OmniStream {

// Subtle cyber blueprint grid background widget
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

        p.setPen(QPen(QColor(25, 33, 44, 180), 1, Qt::DotLine));
        const int step = 20;
        for (int x = 0; x < width(); x += step) {
            p.drawLine(x, 0, x, height());
        }
        for (int y = 0; y < height(); y += step) {
            p.drawLine(0, y, width(), y);
        }

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

        p.setBrush(bgColor);
        p.setPen(QPen(borderColor, 1.0));
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5.0, 5.0);

        QPen iconPen(iconColor, 1.35f, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin);
        p.setPen(iconPen);
        p.setBrush(Qt::NoBrush);

        qreal cx = width() / 2.0;
        qreal cy = height() / 2.0;

        if (m_type == CaptionType::Minimize) {
            p.drawLine(QPointF(cx - 5.0, cy), QPointF(cx + 5.0, cy));
        } else if (m_type == CaptionType::Maximize) {
            if (m_isMaximized) {
                QRectF rBack(cx - 2.5, cy - 4.5, 7.5, 7.5);
                p.drawRoundedRect(rBack, 1.0, 1.0);
                QRectF rFront(cx - 5.0, cy - 2.0, 7.5, 7.5);
                p.fillRect(rFront, isHover ? bgColor : QColor("#090d13"));
                p.drawRoundedRect(rFront, 1.0, 1.0);
            } else {
                QRectF rBox(cx - 5.0, cy - 5.0, 10.0, 10.0);
                p.drawRoundedRect(rBox, 1.2, 1.2);
            }
        } else if (m_type == CaptionType::Close) {
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

protected:
    bool nativeEvent(const QByteArray &eventType, void *message, qintptr *result) override;
    void changeEvent(QEvent *event) override;
    bool eventFilter(QObject *watched, QEvent *event) override;

private slots:
    void onSetupExtensionClicked();
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
    void onImportExcelClicked();
    void onExportExcelClicked();
    void onFilterQueueChanged(const QString& text);
    void onOpenSettingsClicked();
    void onThemeChanged(int index);
    void onDownloadModeChanged(int modeIdx);

    // Context menu actions for queue items
    void showQueueContextMenu(const QPoint& pos);
    void pauseQueueItem(const QString& id);
    void resumeQueueItem(const QString& id);
    void cancelQueueItem(const QString& id);
    void removeQueueItem(const QString& id);
    void playQueueItem(const QString& id);
    void openQueueItemLocation(const QString& id);
    void copyQueueItemUrl(const QString& id);

    // Event updates from Backend
    void onBackendQueueChanged();
    void onBackendItemUpdated(const DownloadItem& item);
    void onBackendLogMessage(const QString& msg);

protected:
    void resizeEvent(QResizeEvent* event) override;
    void moveEvent(QMoveEvent* event) override;
    void closeEvent(QCloseEvent* event) override;

private:
    void setupUI();
    void setupSystemTray();
    void applyStyleSheet(int themeIdx = 0);
    void rebuildQueueCards();
    void updateQueueStats();

    struct CardWidgetRefs {
        QWidget* card = nullptr;
        QLabel* lblStatus = nullptr;
        QLabel* lblPct = nullptr;
        QProgressBar* pBar = nullptr;
        QLabel* lblProgText = nullptr;
        QPushButton* btnAction = nullptr;
    };
    std::unordered_map<std::string, CardWidgetRefs> m_cardMap;

    QSystemTrayIcon* m_trayIcon = nullptr;

    // Window State
    QRect m_normalGeometry;

    // Header Widgets
    QWidget* m_headerWidget = nullptr;
    QLabel* m_lblLogo = nullptr;
    QLabel* m_lblTitle = nullptr;
    QLabel* m_lblVersionBadge = nullptr;
    QPushButton* m_btnSettings = nullptr;
    QComboBox* m_comboTheme = nullptr;
    QLabel* m_lblStatusBadge = nullptr;
    CaptionButton* m_btnCapMin = nullptr;
    CaptionButton* m_btnCapMax = nullptr;
    CaptionButton* m_btnCapClose = nullptr;

    // Notice Banner
    QWidget* m_bannerWidget = nullptr;
    QPushButton* m_btnSetupExtension = nullptr;

    // Card 1: Stream Source
    QWidget* m_card1 = nullptr;
    QPlainTextEdit* m_editUrl = nullptr;
    QPushButton* m_btnPaste = nullptr;

    // Card 2: Configuration
    QWidget* m_card2 = nullptr;
    QLineEdit* m_editTitle = nullptr;
    QComboBox* m_comboRes = nullptr;
    QLineEdit* m_editDir = nullptr;
    QPushButton* m_btnBrowse = nullptr;
    QComboBox* m_comboAudio = nullptr;
    QComboBox* m_comboSubFormat = nullptr;
    QComboBox* m_comboSubLang = nullptr;
    QCheckBox* m_checkEmbedSubs = nullptr;

    // Mode Buttons (8 modes)
    QPushButton* m_btnModeNormal = nullptr;
    QPushButton* m_btnModeNetflix = nullptr;
    QPushButton* m_btnModeTitleOnly = nullptr;
    QPushButton* m_btnModeImdb = nullptr;
    QPushButton* m_btnModeTmdb = nullptr;
    QPushButton* m_btnModeTitleId = nullptr;
    QPushButton* m_btnModeSubMerge = nullptr;
    QPushButton* m_btnModeAuto = nullptr;
    int m_selectedMode = 0;

    // Actions
    QWidget* m_actionWidget = nullptr;
    QPushButton* m_btnStart = nullptr;
    QPushButton* m_btnSubs = nullptr;
    QPushButton* m_btnStop = nullptr;

    // Card 3: Live Progress Card
    QWidget* m_card3 = nullptr;
    QLabel* m_lblProgTitle = nullptr;
    QLabel* m_lblProgStatus = nullptr;
    QLabel* m_lblProgPct = nullptr;
    QProgressBar* m_progBar = nullptr;
    QLabel* m_lblProgSize = nullptr;
    QLabel* m_lblProgSpeed = nullptr;

    // Card 4: Tab Container & Views
    QWidget* m_card4 = nullptr;
    QPushButton* m_btnTabQueue = nullptr;
    QPushButton* m_btnTabTerminal = nullptr;
    QPushButton* m_btnClearLogs = nullptr;

    // Queue Toolbar (All Features!)
    QWidget* m_queueToolbarWidget = nullptr;
    QPushButton* m_btnDownloadAll = nullptr;
    QPushButton* m_btnPauseAll = nullptr;
    QPushButton* m_btnResumeAll = nullptr;
    QPushButton* m_btnStopAll = nullptr;
    QPushButton* m_btnClearQueue = nullptr;
    QPushButton* m_btnFullView = nullptr;
    QPushButton* m_btnImportExcel = nullptr;
    QPushButton* m_btnExportExcel = nullptr;
    QLineEdit* m_editFilterQueue = nullptr;
    QLabel* m_lblQueueStats = nullptr;

    // Views
    QStackedWidget* m_stackedPages = nullptr;
    QWidget* m_pageQueue = nullptr;
    EmptyQueueGridWidget* m_emptyQueuePlaceholder = nullptr;
    QScrollArea* m_queueScrollArea = nullptr;
    QWidget* m_queueCardsContainer = nullptr;
    QVBoxLayout* m_queueCardsLayout = nullptr;
    QPlainTextEdit* m_editTerminal = nullptr;

    // Footer
    QLabel* m_lblFooterBridge = nullptr;
    QLabel* m_lblFooterAuthor = nullptr;

    bool m_isFullView = false;
    QString m_filterText;
    int m_currentTheme = 0; // 0 = Cyber Slate, 1 = Midnight Black
};

} // namespace OmniStream
