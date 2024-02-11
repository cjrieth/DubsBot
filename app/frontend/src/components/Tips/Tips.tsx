import styles from "./Tips.module.css"

export const Tips = () => {
    return (
        <div className={styles.tipsContainer} >
            <ul className={styles.tipsText}>
                <li>The assistant prefers when you use department abreviations. eg: CSE for computer science</li>
            </ul>
            <ul className={styles.tipsText}>
                <li>Start with low complexity questions and get more specific as the conversation continues</li>
            </ul>
            <ul className={styles.tipsText}>
                <li>The assistant excels at finding courses that meet your interests</li>
            </ul>
        </div>
    ) 
}