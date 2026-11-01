#pragma once

#include <QDialog>
#include <QSpinBox>
#include <QLineEdit>
#include <QComboBox>
#include <QCheckBox>
#include <QPushButton>
#include <QLabel>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QFileDialog>
#include "SettingsManager.hpp"

namespace OmniStream {

class SettingsDialog : public QDialog {
    Q_OBJECT
public:
    explicit SettingsDialog(QWidget* parent = nullptr);

private slots:
    void onBrowseFolder();
    void onSave();

private:
    QSpinBox* m_spinConcurrency = nullptr;
    QLineEdit* m_editDefaultDir = nullptr;
    QPushButton* m_btnBrowse = nullptr;
    QComboBox* m_comboSpeedLimit = nullptr;
    QCheckBox* m_checkDeduplication = nullptr;
    QCheckBox* m_checkAutoStart = nullptr;
    QPushButton* m_btnSave = nullptr;
    QPushButton* m_btnCancel = nullptr;

    void setupUI();
};

} // namespace OmniStream

